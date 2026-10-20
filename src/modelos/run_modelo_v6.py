"""run_modelo_v6.py — modelo de consumo esperado con selección automática del mejor
modelo por proceso y nivel (Huber vs GradientBoosting) según R² de prueba.

El mejor modelo de cada celda (proceso × nivel) es el que se guarda en `modelos.pkl`
y el que usa `resultados_modelo`. Se documenta cuál gana y cuándo la línea base
sigue siendo preferible.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.comun.config import leer_tabla  # noqa: E402
from src.modelos.comun_modelos import (  # noqa: E402
    PROCESOS_RC, PROCESO_FA, cfg_modelos, metricas, split_temporal, z_robusto,
)
from src.modelos.fix_agregar_dia_v2 import agregar_dia_con_calendario  # noqa: E402
from src.modelos.fix_agregar_semana import agregar_semana_con_calendario  # noqa: E402
from src.modelos.modelo_esperado_api import features, predecir_modelo  # noqa: E402

INTERIM = RAIZ / "data" / "interim"
DOCS = RAIZ / "documentacion" / "modelos"
CLEAN = RAIZ / "data" / "clean"

R2_ALTA = 0.5      # R² de prueba mínimo para confianza alta (y superar la línea base)
TOL_R2_LB = 0.05   # cuánto puede quedar por debajo de la línea base y seguir contando como "igual"


def confianza(r2, r2_lb):
    """alta: supera la línea base y R² >= R2_ALTA. media: R² positivo y a TOL_R2_LB de la línea base. baja: el resto."""
    if r2 is None or np.isnan(r2):
        return "baja"
    lb = -np.inf if r2_lb is None or np.isnan(r2_lb) else r2_lb
    if r2 > lb and r2 >= R2_ALTA:
        return "alta"
    if r2 > 0 and r2 >= lb - TOL_R2_LB:
        return "media"
    return "baja"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def _tarifa(fechas):
    t = leer_tabla("tarifa_kwh_mensual")
    t["mes"] = pd.to_datetime(t["mes"])
    t = t.sort_values("mes")
    ult = t.loc[t["mes"] <= pd.to_datetime(fechas).max(), "costo_kwh_cop"]
    return float(ult.iloc[-1]) if len(ult) else cfg_modelos()["tarifa_kwh_cop"]


def ajustar_huber(X, y):
    try:
        from sklearn.linear_model import HuberRegressor
        m = HuberRegressor(epsilon=1.35, max_iter=1000)
        m.fit(X, y)
        return {"tipo": "huber", "modelo": m, "columnas": list(X.columns)}
    except Exception:
        coef, *_ = np.linalg.lstsq(np.c_[np.ones(len(X)), X.to_numpy()], y.to_numpy(), rcond=None)
        return {"tipo": "ols", "base": float(coef[0]), "coef": coef[1:], "columnas": list(X.columns)}


def ajustar_arbol(X, y):
    try:
        from sklearn.ensemble import GradientBoostingRegressor
        m = GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=0)
        m.fit(X, y)
        return {"tipo": "gbr", "modelo": m, "columnas": list(X.columns)}
    except Exception:
        return None


def construir_resultados(dm_turno, modelos, conf_turno=None):
    filas = []
    for proc in PROCESOS_RC + [PROCESO_FA]:
        tab = dm_turno[dm_turno["proceso_modelo"] == proc].sort_values(["fecha_turno", "turno"]).copy()
        if tab.empty or f"turno|{proc}" not in modelos:
            continue
        m = modelos[f"turno|{proc}"]["mejor"]
        tab["kwh_esperado"] = np.clip(predecir_modelo(m, features(tab, "turno")), 0, None)
        tab["exceso_kwh"] = tab["kwh"] - tab["kwh_esperado"]
        pct = np.where(tab["kwh_esperado"] > 0, 100 * tab["exceso_kwh"] / tab["kwh_esperado"], np.nan)
        tab["exceso_pct"] = np.clip(pct, -100, 200)
        filas.append(tab)
    if not filas:
        return pd.DataFrame()
    out = pd.concat(filas, ignore_index=True)
    out["confianza_modelo"] = out["proceso_modelo"].map(conf_turno or {}).fillna("baja")
    out["puntaje_anomalia"] = 0.0
    for proc, g in out.groupby("proceso_modelo"):
        z = np.abs(z_robusto(g["kwh"] - g["kwh_esperado"].to_numpy()))
        out.loc[g.index, "puntaje_anomalia"] = np.clip(1 - np.exp(-z / 10), 0, 1).round(4)
    out["es_anomalia"] = (out["puntaje_anomalia"] >= 0.5).astype(int)
    tarifa = _tarifa(out["fecha_turno"])
    out["costo_exceso_cop"] = np.clip(out["exceso_kwh"], 0, None) * tarifa
    out["severidad"] = "baja"
    for proc, g in out.groupby("proceso_modelo"):
        costo = g["costo_exceso_cop"]
        p50, p90 = costo.quantile(0.5), costo.quantile(0.9)
        out.loc[g.index, "severidad"] = np.where(costo >= p90, "alta", np.where(costo >= p50, "media", "baja"))
    out.loc[out["es_anomalia"] == 0, "severidad"] = "baja"
    return out


def main():
    dm = leer_tabla("dataset_modelo")
    dm = dm[dm["proceso_modelo"].isin(PROCESOS_RC + [PROCESO_FA])].copy()
    dm.loc[dm["proceso_modelo"] == PROCESO_FA, "planta"] = "F&A"
    dm = dm.sort_values(["proceso_modelo", "fecha_turno", "turno"])

    modelos, veredictos = {}, []
    lineas = ["# 03 · Modelo de consumo esperado (Joshua)", "",
             "Regresión robusta (Huber) y GradientBoosting por proceso y nivel. Se elige el **mejor modelo "
             "por celda (proceso × nivel)** según R² de la prueba (jul–sep 2026). Rezagos causales de "
             "producción (t−1, t−2). Sin `operando` ni régimen (fuga de información).", "",
             "## Métricas en prueba y modelo elegido", "",
             "| nivel | proceso | modelo | n_pru | MAE | WAPE % | R² | R²_línea_base | elegido |",
             "|---|---|---|---|---|---|---|---|---|"]

    try:
        with open(INTERIM / "linea_base.pkl", "rb") as f:
            _lb = pickle.load(f)
        lb_r2 = {(n, p): mp.get("r2") for n, p, _me, mp in _lb.get("metricas", [])}
    except FileNotFoundError:
        lb_r2 = {}

    for nivel in ("turno", "dia", "semana"):
        if nivel == "turno":
            tab_nivel = dm[dm["calidad_ok"] == 1]
        elif nivel == "dia":
            tab_nivel = agregar_dia_con_calendario(dm)
            tab_nivel = tab_nivel[tab_nivel["calidad_ok"] == 1]
        else:
            tab_nivel = agregar_semana_con_calendario(dm).rename(columns={"semana_inicio": "fecha_turno"})
            tab_nivel = tab_nivel[tab_nivel["calidad_ok"] == 1]
        ent, pru = split_temporal(tab_nivel, "fecha_turno")
        for proc in PROCESOS_RC + [PROCESO_FA]:
            e = ent[ent["proceso_modelo"] == proc]
            p = pru[pru["proceso_modelo"] == proc]
            if e.empty or p.empty:
                continue
            Xe, ye = features(e, nivel), e["kwh"]
            Xp, yp = features(p, nivel), p["kwh"]
            m_h = ajustar_huber(Xe, ye)
            m_a = ajustar_arbol(Xe, ye)
            cand = {"huber": m_h}
            if m_a is not None:
                cand["gbr"] = m_a
            resumen_local = {}
            for nombre, mm in cand.items():
                resumen_local[nombre] = metricas(yp, np.clip(predecir_modelo(mm, Xp), 0, None))
            mejor_nombre = max(resumen_local, key=lambda k: (resumen_local[k]["r2"] if not np.isnan(resumen_local[k]["r2"]) else -np.inf))
            # cuantiles 10 y 90 de los residuos del modelo elegido sobre todos los periodos válidos de la celda:
            # son el intervalo de `pronostico` y de `predecir()`
            todo = tab_nivel[tab_nivel["proceso_modelo"] == proc]
            resid = todo["kwh"].to_numpy() - np.clip(predecir_modelo(cand[mejor_nombre], features(todo, nivel)), 0, None)
            modelos[f"{nivel}|{proc}"] = {"huber": m_h, "arbol": m_a, "mejor": cand[mejor_nombre],
                                          "nivel": nivel, "mejor_nombre": mejor_nombre,
                                          "q10": float(np.quantile(resid, 0.10)), "q90": float(np.quantile(resid, 0.90))}
            r2_lb = lb_r2.get((nivel, proc), np.nan)
            r2_el = resumen_local[mejor_nombre]["r2"]
            veredictos.append({"nivel": nivel, "proceso": proc, "elegido": mejor_nombre, "R²": round(float(r2_el), 4),
                               "R² línea base": r2_lb,
                               "supera la línea base": "sí" if (not np.isnan(r2_el) and (np.isnan(r2_lb) or r2_el > r2_lb)) else "no",
                               "confianza": confianza(r2_el, r2_lb)})
            for nombre in ("huber", "gbr"):
                if nombre not in resumen_local:
                    continue
                mp = resumen_local[nombre]
                elegido = "✓" if nombre == mejor_nombre else ""
                lineas.append(f"| {nivel} | {proc} | {nombre} | {mp['n']} | {mp['mae']} | {mp['wape']} | {mp['r2']} | {r2_lb} | {elegido} |")

    conf_turno = {v["proceso"]: v["confianza"] for v in veredictos if v["nivel"] == "turno"}
    resultados = construir_resultados(dm[dm["calidad_ok"] == 1], modelos, conf_turno)
    if not resultados.empty:
        cols = ["fecha_turno", "turno", "planta", "proceso_modelo", "kwh", "kwh_esperado",
                "exceso_kwh", "exceso_pct", "puntaje_anomalia", "es_anomalia", "severidad", "costo_exceso_cop", "confianza_modelo"]
        out = resultados[cols].rename(columns={"kwh": "kwh_real"}).copy()
        for c in ("exceso_kwh", "exceso_pct"):
            out[c] = out[c].round(2)
        out["costo_exceso_cop"] = out["costo_exceso_cop"].round(0)
        out["kwh_real"] = out["kwh_real"].round(3)
        out["kwh_esperado"] = out["kwh_esperado"].round(3)
        out.to_csv(CLEAN / "resultados_modelo.csv", index=False)
        print(f"Escrito {CLEAN / 'resultados_modelo.csv'} ({len(out)} filas)")

    ver = pd.DataFrame(veredictos)
    resumen_ver = ver.groupby("nivel")["supera la línea base"].apply(lambda s: f"{(s == 'sí').sum()} de {len(s)}")
    lineas += ["", "## ¿Supera a la línea base? (R² en la prueba jul–sep 2026)", "",
               "Para cada proceso y nivel, el modelo elegido contra la línea base. `confianza` es la que lleva la columna "
               f"`confianza_modelo` de `resultados_modelo` (nivel turno): **alta** si supera la línea base con R² de {R2_ALTA} o más; "
               f"**media** si la iguala (a {TOL_R2_LB}) con R² positivo; **baja** en otro caso. Con `baja`, el exceso de ese "
               "proceso es indicativo, y para un uso crítico conviene la línea base.", "",
               md_tabla(ver), "",
               "Procesos que superan la línea base: " + "; ".join(f"{n} {v}" for n, v in resumen_ver.items()) + ".", ""]
    lineas += ["", "## Notas y supuestos", "",
               "- `resultados_modelo` se genera a nivel **turno** (RC y F&A) para el dashboard y las alertas, "
               "usando el modelo elegido por celda (proceso × nivel).",
               "- El costo del exceso usa la tarifa de Clarios (`tarifa_kwh_mensual`).",
               "- `puntaje_anomalia` es 1−exp(−|z_robusto|/10), robusto a la desviación MAD por proceso.",
               "- **`exceso_pct` está acotado a [-100, 200]%** para legibilidad; cuando `kwh_esperado` "
               "es muy bajo (inicio de semana o parada corta) el porcentaje puede ser enorme aunque el "
               "exceso en kWh sea pequeño: el dashboard y las alertas deben priorizar **kWh y COP**, no el %.",
               "- La regresión Huber no fuerza `base ≥ 0`; en algunos procesos la predicción mínima puede "
               "ser 0 tras el clip, lo que hace que `exceso_kwh = kwh_real`. Esto es esperado y se marca "
               "como limitación: el modelo no distingue bien paradas muy cortas.",
               "- **Selección automática del mejor modelo:** el `✓` marca cuál de los dos (huber o gbr) "
               "gana en R² de prueba para esa celda; ese es el que se usa en `resultados_modelo` y en "
               "`predecir()`. Como la elección se hace con la misma prueba con que se reportan las métricas, "
               "**esas métricas son algo optimistas**. Si un proceso no supera la línea base, se recomienda usar la línea base "
               "para ese proceso (Plan B de `documentacion/00_plan_de_trabajo.md`); la columna `confianza_modelo` lo señala.",
               "- **Dentro y fuera de muestra:** `resultados_modelo` calcula el exceso de todos los turnos con el modelo ya "
               "ajustado; los meses de entrenamiento (oct 2025 a jun 2026) quedan *dentro de muestra*, y solo jul a sep 2026 es "
               "una predicción real.",
               "- **F&A (formación) queda fuera:** el entrenamiento va de oct 2025 a jun 2026 y F&A solo tiene datos de jul a "
               "sep 2026; su análisis es `fa_encendido.md`.", ""]

    INTERIM.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(INTERIM / "modelos.pkl", "wb") as f:
        pickle.dump(modelos, f)
    (DOCS / "03_modelo_esperado.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escritos {DOCS / '03_modelo_esperado.md'} y {INTERIM / 'modelos.pkl'}")
    print("\n".join(lineas[:35]))


if __name__ == "__main__":
    main()
