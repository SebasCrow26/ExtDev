"""run_pronostico_v2.py — pronóstico por escenarios, metas y exceso/ahorro (Joshua; revisado en la auditoría final).

Cambios frente a la versión anterior (con su motivo):
  - El pronóstico armaba la fila del día siguiente copiando la última fila real: dejaba el día de la semana del último
    día observado y los rezagos de producción (t-1, t-2) en cero, lo que subestimaba el consumo (triturado -38 %,
    horno -13 %, refinación -13 % en el primer día). Ahora la fila futura trae su propio calendario y se agrega a la
    serie real, así los rezagos salen de la producción previa.
  - El horizonte pasa de 1 día a `modelos.horizonte_pronostico_dias` (7), y la producción supuesta de cada día es el
    promedio del mismo día de la semana en las últimas SEMANAS_REFERENCIA semanas (antes: media de 30 días, que mete
    los fines de semana en todos los días).
  - El ahorro potencial se calcula sobre el exceso NETO (exceso menos defecto), no sobre la suma de excesos positivos,
    porque esa suma incluye el error del propio modelo (ver documentacion/modelos/05_pronostico_y_ahorro.md).
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import cargar_config, leer_tabla  # noqa: E402
from src.modelos.comun_modelos import (  # noqa: E402
    PROCESOS_RC, PROCESO_FA, cfg_modelos,
)
from src.modelos.fix_agregar_dia_v2 import agregar_dia_con_calendario  # noqa: E402
from src.modelos.modelo_esperado_api import features, predecir_modelo  # noqa: E402

INTERIM = RAIZ / "data" / "interim"
DOCS = RAIZ / "documentacion" / "modelos"
CLEAN = RAIZ / "data" / "clean"

SEMANAS_REFERENCIA = 4  # semanas hacia atrás para promediar la producción de cada día de la semana
ESCENARIOS = (("bajo", 0.85), ("base", 1.0), ("alto", 1.15))


def _tarifa():
    t = leer_tabla("tarifa_kwh_mensual")
    t["mes"] = pd.to_datetime(t["mes"])
    t = t.sort_values("mes")
    return float(t["costo_kwh_cop"].iloc[-1]) if len(t) else cfg_modelos()["tarifa_kwh_cop"]


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def produccion_por_dia(tab: pd.DataFrame, fechas, semanas: int = SEMANAS_REFERENCIA) -> list[float]:
    """Producción supuesta de cada fecha: promedio del mismo día de la semana en las últimas `semanas` semanas."""
    ult = tab["fecha_turno"].max()
    rec = tab[tab["fecha_turno"] > ult - pd.Timedelta(days=7 * semanas)]
    p = rec["produccion"].clip(lower=0)
    media_global = float(p.mean()) if len(p) else 0.0
    por_dia = p.groupby(rec["dia_semana"]).mean()
    return [float(por_dia.get(pd.Timestamp(f).dayofweek, media_global)) for f in fechas]


def agregar_dias_futuros(tab: pd.DataFrame, fechas, produccion, festivos) -> pd.DataFrame:
    """Agrega a la serie real una fila por fecha futura con su propio calendario y la producción supuesta.

    Así `features()` calcula los rezagos de producción (t-1, t-2) con la producción previa (real o supuesta) y el día
    de la semana, fin de semana y festivo de la fecha pronosticada, no los del último día observado.
    """
    base = tab.sort_values("fecha_turno").reset_index(drop=True)
    plantilla = base.iloc[-1]
    nuevas = []
    for fecha, prod in zip(fechas, produccion):
        f = pd.Timestamp(fecha)
        fila = plantilla.copy()
        fila["fecha_turno"] = f
        fila["produccion"] = prod
        fila["dia_semana"] = f.dayofweek
        fila["es_fin_semana"] = int(f.dayofweek >= 5)
        fila["es_festivo"] = int(f.date() in festivos)
        nuevas.append(fila)
    return pd.concat([base, pd.DataFrame(nuevas)], ignore_index=True)


def resumen_exceso(res: pd.DataFrame, fin_entrenamiento=None) -> dict:
    """Exceso positivo, defecto (negativo) y neto de `resultados_modelo`, total, por proceso y por periodo."""
    e = res["exceso_kwh"].fillna(0)
    out = {"pos": float(e.clip(lower=0).sum()), "neg": float(e.clip(upper=0).sum()), "real": float(res["kwh_real"].sum())}
    out["neto"] = out["pos"] + out["neg"]
    g = res.assign(_pos=e.clip(lower=0), _neg=e.clip(upper=0)).groupby("proceso_modelo").agg(
        real=("kwh_real", "sum"), pos=("_pos", "sum"), neg=("_neg", "sum"))
    g["neto"] = g["pos"] + g["neg"]
    out["por_proceso"] = g
    if fin_entrenamiento is not None:
        f = pd.to_datetime(res["fecha_turno"])
        corte = pd.Timestamp(fin_entrenamiento)
        out["neto_entrenamiento"] = float(e[f <= corte].sum())
        out["neto_prueba"] = float(e[f > corte].sum())
    return out


def main():
    cfg = cfg_modelos()
    cfg_all = cargar_config()
    horizonte = int(cfg_all["modelos"]["horizonte_pronostico_dias"])
    from src.modelos.modelo_esperado_api import cargar_modelos
    modelos = cargar_modelos()
    dm = leer_tabla("dataset_modelo")
    dm = dm[dm["proceso_modelo"].isin(PROCESOS_RC + [PROCESO_FA])].copy()
    dm.loc[dm["proceso_modelo"] == PROCESO_FA, "planta"] = "F&A"

    dia = agregar_dia_con_calendario(dm)
    dia = dia[dia["calidad_ok"] == 1].sort_values(["proceso_modelo", "fecha_turno"])
    anios = range(dia["fecha_turno"].min().year, dia["fecha_turno"].max().year + 2)
    festivos = holidays.country_holidays(cfg_all["calendario"]["pais_festivos"], years=anios)

    lineas = ["# 05 · Pronóstico, metas y ahorro potencial (Joshua)", "",
             f"El pronóstico evalúa la función de consumo esperado sobre una **producción supuesta** durante los "
             f"próximos **{horizonte} días** (escenarios `bajo`/`base`/`alto`, o `plan` si Clarios lo cargara). "
             f"La producción supuesta de cada día es el **promedio del mismo día de la semana en las últimas "
             f"{SEMANAS_REFERENCIA} semanas** por un factor de escenario (0.85, 1.0, 1.15). El intervalo sale de los "
             f"cuantiles 10 y 90 de los residuos de entrenamiento (nivel día). Cada día usa su propio calendario "
             f"(día de la semana, fin de semana, festivo) y los rezagos de producción de los días anteriores.", ""]

    filas, sin_modelo = [], []
    for proc in PROCESOS_RC + [PROCESO_FA]:
        tab = dia[dia["proceso_modelo"] == proc].sort_values("fecha_turno").copy()
        if tab.empty or f"dia|{proc}" not in modelos:
            sin_modelo.append(proc)
            continue
        m = modelos[f"dia|{proc}"]["mejor"]
        X = features(tab, "dia")
        pred = np.clip(predecir_modelo(m, X), 0, None)
        resid = tab["kwh"].to_numpy() - pred
        celda = modelos[f"dia|{proc}"]
        if "q10" in celda and "q90" in celda:  # el modelo entregado trae su intervalo: así el pronóstico y predecir() coinciden
            q10, q90 = float(celda["q10"]), float(celda["q90"])
        else:
            q10, q90 = float(np.quantile(resid, 0.10)), float(np.quantile(resid, 0.90))

        ultimo = tab["fecha_turno"].max()
        fechas = [ultimo + pd.Timedelta(days=d) for d in range(1, horizonte + 1)]
        prod_base = produccion_por_dia(tab, fechas)
        for escenario, factor in ESCENARIOS:
            prods = [p * factor for p in prod_base]
            serie = agregar_dias_futuros(tab, fechas, prods, festivos)
            pf = np.clip(predecir_modelo(m, features(serie, "dia").iloc[-horizonte:]), 0, None)
            for fecha, prod, p in zip(fechas, prods, pf):
                filas.append({"fecha": str(fecha.date()), "planta": tab["planta"].iloc[0],
                              "proceso_modelo": proc, "escenario": escenario,
                              "produccion_supuesta": round(prod, 1),
                              "kwh_pronosticado": round(float(p), 1),
                              "kwh_inferior": round(max(float(p) + q10, 0), 1),
                              "kwh_superior": round(float(p) + q90, 1)})

    pron = pd.DataFrame(filas)
    pron.to_csv(CLEAN / "pronostico.csv", index=False)
    print(f"Escrito {CLEAN / 'pronostico.csv'} ({len(pron)} filas)")

    metas_filas = []
    for proc in PROCESOS_RC + [PROCESO_FA]:
        tab = dia[dia["proceso_modelo"] == proc]
        prod = tab["produccion"].where(tab["produccion"] > 0)
        kpu = (tab["kwh"] / prod).replace([np.inf, -np.inf], np.nan).dropna()
        if kpu.empty:
            continue
        meta = float(np.percentile(kpu, cfg["percentil_meta"]))
        metas_filas.append({"planta": tab["planta"].iloc[0], "proceso_modelo": proc,
                            "meta_kwh_por_unidad": round(meta, 4), "fuente": "historico_p25",
                            "vigente_desde": str(tab["fecha_turno"].min().date())})
    metas = pd.DataFrame(metas_filas)
    metas.to_csv(CLEAN / "metas.csv", index=False)
    print(f"Escrito {CLEAN / 'metas.csv'} ({len(metas)} filas)")

    res = pd.read_csv(CLEAN / "resultados_modelo.csv")
    ex = resumen_exceso(res, cfg["fin_entrenamiento"])
    tarifa = _tarifa()
    ahorro = max(ex["neto"], 0) * tarifa * cfg["fraccion_evitable"]
    por = ex["por_proceso"].copy()
    conf = res.groupby("proceso_modelo")["confianza_modelo"].first() if "confianza_modelo" in res.columns else None
    tabla_proc = por.round(0).astype(int).reset_index()
    tabla_proc.columns = ["proceso", "kWh real", "exceso positivo (kWh)", "defecto (kWh)", "neto (kWh)"]
    if conf is not None:
        tabla_proc["confianza del modelo"] = tabla_proc["proceso"].map(conf)

    nota_fa = (f"- Sin pronóstico diario: {', '.join(sin_modelo)}. El modelo diario se entrena con octubre de 2025 a junio de 2026 y "
               "F&A solo tiene datos de julio a septiembre de 2026; su análisis está en `fa_encendido.md` y su meta en `metas.csv`."
               if sin_modelo else "")
    lineas += ([nota_fa, ""] if nota_fa else []) + [
        f"## Pronóstico ({horizonte} días, producción del mismo día de la semana × factor)", "",
        md_tabla(pron), "",
        "## Metas (percentil 25 histórico del kWh por unidad)", "",
        md_tabla(metas), "",
        "## Exceso de consumo y ahorro potencial (escenario)", "",
        f"- Exceso **bruto** (suma de los turnos por encima de lo esperado): {ex['pos']:,.0f} kWh. "
        "**No es un ahorro:** incluye el error del propio modelo.",
        f"- Defecto (turnos por debajo de lo esperado): {ex['neg']:,.0f} kWh. Compensa el {abs(ex['neg']) / ex['pos']:.0%} del exceso bruto.",
        f"- **Exceso neto** = {ex['neto']:,.0f} kWh, el {ex['neto'] / ex['real']:.1%} de la energía real "
        f"({ex['real']:,.0f} kWh) en `resultados_modelo` (turnos con calidad_ok).",
        f"- Neto en los meses de entrenamiento (hasta {cfg['fin_entrenamiento']}, modelo ajustado con esos mismos datos): "
        f"{ex['neto_entrenamiento']:,.0f} kWh. Neto en la prueba (después, fuera de muestra): {ex['neto_prueba']:,.0f} kWh.",
        f"- Tarifa usada: **{tarifa:.1f} COP/kWh** (última disponible de `tarifa_kwh_mensual`).",
        f"- `fraccion_evitable` = **{cfg['fraccion_evitable']}** (parámetro **supuesto** de config.yaml).",
        f"- **Ahorro potencial (escenario) = máx(neto, 0) × tarifa × fracción = {ahorro:,.0f} COP**.", "",
        md_tabla(tabla_proc), "",
        "> `fraccion_evitable` es un relleno sin respaldo de Clarios (ver advertencia del parámetro). "
        "Este ahorro es un **escenario**, no un ahorro demostrado. El exceso neto es un orden de magnitud: "
        "un modelo con error siempre deja turnos por encima y por debajo de lo esperado, y solo la diferencia "
        "neta puede apuntar a un consumo mayor al esperado. Los procesos con confianza del modelo `baja` "
        "(modelo peor que la línea base) deben leerse como indicativos.", "",
        "## Metas: advertencia", "",
        "`metas_clarios.csv` trae presupuestos de kWh por equivalente **por planta y mes** "
        "(Ensamble 2.012, OREC 5.861, F&A 18.332), no por turno; la base trae además presupuestos por línea o proceso "
        "(G6 de `documentacion/11_cifras_verificadas.md`), que no están en `metas_clarios.csv`. Para RC y por proceso "
        "se deriva del histórico (`historico_p25`), como pide la especificación.", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "05_pronostico_y_ahorro.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / '05_pronostico_y_ahorro.md'}")
    print(f"Exceso: bruto {ex['pos']:,.0f} | defecto {ex['neg']:,.0f} | neto {ex['neto']:,.0f} kWh | ahorro escenario {ahorro:,.0f} COP")


if __name__ == "__main__":
    main()
