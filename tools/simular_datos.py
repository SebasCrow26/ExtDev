"""Genera datos SIMULADOS (inventados) con el mismo formato que las tablas de data/clean.

No usa ningún dato de Clarios: la producción, los contadores del SCADA, el gas y las series mensuales se inventan con una semilla
fija. Lo que sí reutiliza es el CÓDIGO del proyecto, para que los datos simulados pasen por la misma cadena que los reales:
  contadores acumulados -> limpieza (energia_comun) -> energia_turno -> dataset_modelo (03_dataset_modelo) -> resultados_modelo
  (modelos ya entrenados, solo inferencia) -> pronóstico, metas y tablas de calidad.

Para que los modelos ya entrenados den esperados razonables, el consumo de cada turno se simula alrededor de lo que esos modelos
esperan (más ruido, anomalías inyectadas y paradas). Los modelos entrenados se leen de data/interim/modelos.pkl.

Uso (desde la raíz del repositorio):
    python tools/simular_datos.py --salida C:/ruta/corta/simulado
Deja las tablas en <salida>/data/clean. La semilla fija hace que dos ejecuciones den lo mismo.
"""
import argparse
import pickle
import runpy
import shutil
import sys
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
INI, FIN = pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-30")
INI_FA = pd.Timestamp("2026-07-02")
HORAS_TURNO = {1: range(6, 14), 2: range(14, 22), 3: list(range(22, 24)) + list(range(0, 6))}
# proceso -> (medidores y su parte del consumo)
MEDIDORES = {"triturado": {"TRITURADO": 1.0}, "horno": {"HORNO": 1.0}, "refinacion": {"REFINO_1": 0.97, "REFINO_2": 0.03},
             "filtros": {"FILTRO_1": 0.74, "FILTRO_2": 0.26}, "ptari": {"PTARI": 1.0}}
LINEAS = {"triturado": ["RCTRIT01"], "horno": ["RCFUND02"], "refinacion": ["RCREFI01", "RCREFI02", "RCREFI03"]}
PRODUCCION_DIARIA_KG = {"triturado": 69000, "horno": 66000, "refinacion": 59000}
DIAS_OPERA = {"triturado": range(0, 6), "horno": range(0, 6), "refinacion": range(0, 5)}   # lunes = 0
CONFIANZA = {"horno": "alta", "triturado": "media", "ptari": "media", "refinacion": "baja", "filtros": "baja"}
RESETS = {"TRITURADO": 12, "REFINO_1": 12, "REFINO_2": 12, "FILTRO_1": 3, "FILTRO_2": 10, "HORNO": 1, "PTARI": 1}


def preparar_arbol(salida):
    """Copia el código del proyecto a la carpeta de salida para ejecutarlo con rutas propias (sin tocar data/ del repositorio)."""
    if salida.exists():
        shutil.rmtree(salida)
    for carpeta in ("src", "config", "tools"):
        shutil.copytree(REPO / carpeta, salida / carpeta, ignore=shutil.ignore_patterns("__pycache__", "archivo"))
    for sub in ("data/clean", "data/interim", "modelos", "documentacion/modelos", "documentacion/figuras/eda_rc", "documentacion/figuras/eda_fa_gas"):
        (salida / sub).mkdir(parents=True, exist_ok=True)
    modelos = REPO / "modelos" / "modelos.pkl"
    if not modelos.exists():
        sys.exit("Falta modelos/modelos.pkl (los modelos ya entrenados, que no se reentrenan).")
    shutil.copy(modelos, salida / "modelos" / "modelos.pkl")


def turno_de(ts):
    h = ts.hour
    return 1 if 6 <= h < 14 else 2 if 14 <= h < 22 else 3


def fecha_turno(ts):
    return (ts - pd.Timedelta(days=1)).normalize() if ts.hour < 6 else ts.normalize()


# ---------------------------------------------------------------------------------------------- producción
def simular_produccion_rc(rng, festivos):
    filas, dias = [], pd.date_range(INI, FIN)
    for proc, media in PRODUCCION_DIARIA_KG.items():
        for d in dias:
            paro_navidad = pd.Timestamp("2025-12-24") <= d <= pd.Timestamp("2026-01-02")
            if d.dayofweek not in DIAS_OPERA[proc] or d.date() in festivos or paro_navidad or rng.random() > 0.62:
                continue
            total = media / 0.62 * rng.lognormal(-0.125, 0.5)
            turnos = rng.choice([1, 2, 3], size=rng.choice([1, 2], p=[0.7, 0.3]), replace=False, p=[0.35, 0.4, 0.25])
            partes = rng.dirichlet(np.ones(len(turnos))) * total
            for t, cant in zip(turnos, partes):
                lineas = LINEAS[proc]
                reparto = rng.dirichlet(np.ones(len(lineas))) if len(lineas) > 1 else np.array([1.0])
                for ln, f in zip(lineas, reparto):
                    filas.append({"fecha_turno": d, "turno": int(t), "planta": "RC", "linea_erp": ln, "proceso_modelo": proc,
                                  "categoria_equs": "PLOMO", "cantidad": round(float(cant * f), 1), "unidad": "kg",
                                  "n_transacciones": int(rng.integers(1, 4)), "n_fecha_ajustada": 0})
    return pd.DataFrame(filas)


def simular_produccion_fa(rng):
    filas = []
    for d in pd.date_range(INI_FA, FIN):
        for t in (1, 2, 3):
            encendido = (d.dayofweek in range(1, 5)) or (d.dayofweek == 6 and t == 3) or (d.dayofweek == 0) or (d.dayofweek == 5 and t == 1)
            if encendido and not (d.dayofweek == 6 and t < 3):
                filas.append({"fecha_turno": d, "turno": t, "planta": "F&A", "linea_erp": "FAFORM02", "proceso_modelo": "formacion",
                              "categoria_equs": "FORMACION", "cantidad": float(round(rng.normal(3400, 500))), "unidad": "unidades",
                              "n_transacciones": int(rng.integers(8, 17)), "n_fecha_ajustada": 0})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------------------------- consumo por turno
def consumo_rc(rng, prod, festivos, modelos, features, predecir_modelo, asociados):
    """kWh de cada turno y proceso: lo que esperan los modelos entrenados, con ruido, anomalías y paradas inyectadas."""
    idx = pd.MultiIndex.from_product([pd.date_range(INI - pd.Timedelta(days=1), FIN), [1, 2, 3]], names=["fecha_turno", "turno"]).to_frame(index=False)
    out = []
    for proc in MEDIDORES:
        fuente = asociados.get(proc, proc)
        p = prod[prod["proceso_modelo"] == fuente].groupby(["fecha_turno", "turno"])["cantidad"].sum().rename("produccion").reset_index()
        tab = idx.merge(p, on=["fecha_turno", "turno"], how="left").fillna({"produccion": 0.0})
        tab["proceso_modelo"] = proc
        tab["dia_semana"] = tab["fecha_turno"].dt.dayofweek
        tab["es_fin_semana"] = (tab["dia_semana"] >= 5).astype(int)
        tab["es_festivo"] = tab["fecha_turno"].dt.date.map(lambda d: int(d in festivos))
        esperado = np.clip(predecir_modelo(modelos[f"turno|{proc}"]["mejor"], features(tab, "turno")), 0, None)
        # ruido de dispersión constante por proceso (no proporcional al consumo): así la regla robusta de anomalías no marca turnos normales
        sd = 0.12 * float(np.median(esperado[esperado > 20])) if (esperado > 20).any() else 5.0
        kwh = esperado + rng.normal(0, sd, len(tab)) + np.abs(rng.normal(3, 1.5, len(tab)))
        n = len(tab)
        # episodios de exceso sostenido, pocas anomalías puntuales y paradas inesperadas en días de semana
        for _ in range(rng.integers(5, 9)):
            a = int(rng.integers(0, n - 10)); kwh[a:a + int(rng.integers(4, 9))] += rng.uniform(0.25, 0.5) * max(float(np.median(esperado[esperado > 20])), 20) if (esperado > 20).any() else 0
        altos = tab.index[(tab["es_fin_semana"] == 0) & (esperado > 0.7 * (np.median(esperado[esperado > 20]) if (esperado > 20).any() else 1e9))].to_numpy()
        for a in rng.choice(altos, size=min(3, len(altos)), replace=False) if len(altos) else []:
            kwh[a] += rng.uniform(4, 7) * sd
        for a in (rng.choice(altos, size=min(3, len(altos)), replace=False) if len(altos) else []):
            kwh[a:a + int(rng.integers(2, 4))] *= 0.03   # parada inesperada: consumo casi cero donde lo típico es alto
        if proc == "triturado":   # triturado funcionando en domingo
            for a in rng.choice(tab.index[(tab["dia_semana"] == 6) & (tab["turno"] == 2)].to_numpy(), 5, replace=False):
                kwh[a] = rng.uniform(450, 880)
        tab["kwh"] = np.clip(kwh, 0, None)
        out.append(tab)
    return pd.concat(out, ignore_index=True)


def consumo_fa(rng):
    filas = []
    for d in pd.date_range(INI_FA, FIN):
        for t in (1, 2, 3):
            enc = (d.dayofweek in (0, 1, 2, 3, 4)) or (d.dayofweek == 5 and t == 1) or (d.dayofweek == 6 and t == 3)
            filas.append({"fecha_turno": d, "turno": t, "kwh": max(rng.normal(16600, 2100), 0) if enc else abs(rng.normal(250, 120))})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------------------------- contadores del SCADA
def contadores(rng, kwh_turno, medidores, inicio, fin, minuto, eventos):
    """Contadores acumulados en Wh, con una lectura por hora: reinicios, un congelamiento general y uno de un solo medidor."""
    horas = pd.date_range(inicio.normalize() + pd.Timedelta(hours=0), fin.normalize() + pd.Timedelta(hours=23), freq="h")
    por_hora = {m: np.zeros(len(horas)) for m in medidores}
    pos = {h: i for i, h in enumerate(horas)}
    for (proc, f, t), kwh in kwh_turno.items():
        pesos = rng.normal(1, 0.12, 8).clip(0.3)
        pesos = pesos / pesos.sum()
        for h, w in zip(HORAS_TURNO[t], pesos):
            ts = f + pd.Timedelta(days=1 if h < 6 else 0, hours=h)
            if ts in pos:
                for m, share in medidores_de(proc).items():
                    if m in por_hora:
                        por_hora[m][pos[ts]] += kwh * share * w
    marcas = horas + pd.Timedelta(minutes=minuto)
    datos = {}
    for m, v in por_hora.items():
        acum = rng.uniform(2e9, 2.5e10) + np.cumsum(v * 1000.0) - 0.5 * v * 1000.0
        rep = acum.copy()
        for i in sorted(rng.integers(50, len(rep) - 50, eventos["resets"].get(m, 0))):
            rep[i:] -= rep[i] - rng.uniform(500, 6000)
        datos[m] = rep
    df = pd.DataFrame({"t": marcas, **datos})
    for (inicio_c, horas_c, meds) in eventos["congelamientos"]:
        a = int((pd.Timestamp(inicio_c) - horas[0]).total_seconds() // 3600)
        for m in meds:
            if m in df.columns:
                df.loc[a:a + horas_c - 1, m] = df.loc[a - 1, m]
    for m in df.columns[1:]:
        df[m] = df[m].round(0)
    return df


def medidores_de(proc):
    return MEDIDORES.get(proc, {})


# ---------------------------------------------------------------------------------------------- principal
def main(salida):
    salida = Path(salida)
    preparar_arbol(salida)
    sys.path.insert(0, str(salida))
    for mod in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
        del sys.modules[mod]
    from src.comun.config import cargar_config, tabla_mapa_procesos
    from src.datos import energia_comun as ec
    from src.modelos.modelo_esperado_api import features, predecir_modelo

    CLEAN = salida / "data" / "clean"
    cfg = cargar_config()
    cal, rac, k = cfg["calidad"], cfg["rachas"], cfg["unidades"]["contador_energia_a_kwh"]
    rng = np.random.default_rng(2026)
    festivos = holidays.country_holidays("CO", years=[2025, 2026])
    modelos = pickle.load(open(salida / "modelos" / "modelos.pkl", "rb"))
    asociados = cfg["modelado"]["procesos_asociados"]

    # --- producción y consumo por turno
    prod = pd.concat([simular_produccion_rc(rng, festivos), simular_produccion_fa(rng)], ignore_index=True)
    rc = consumo_rc(rng, prod, festivos, modelos, features, predecir_modelo, asociados)
    fa = consumo_fa(rng)

    # --- contadores y limpieza (el mismo código que usan los datos reales)
    kt = {(r.proceso_modelo, r.fecha_turno, int(r.turno)): r.kwh for r in rc.itertuples()}
    ev_rc = {"resets": RESETS, "congelamientos": [("2026-01-14 06:00", 36, list(RESETS)), ("2026-05-05 08:00", 20, ["FILTRO_2"])]}
    meds_rc = [m for d in MEDIDORES.values() for m in d]
    df_rc = contadores(rng, kt, {m: 1 for m in meds_rc}, INI - pd.Timedelta(days=1), FIN, 31, ev_rc)
    kt_fa = {("formacion", r.fecha_turno, int(r.turno)): r.kwh for r in fa.itertuples()}
    meds_fa = ["RECTIFICADOR_1", "RECTIFICADOR_2", "RECTIFICADOR_3"]
    MEDIDORES.update({"formacion": {"RECTIFICADOR_1": 0.35, "RECTIFICADOR_2": 0.35, "RECTIFICADOR_3": 0.30}})
    df_fa = contadores(rng, kt_fa, {m: 1 for m in meds_fa}, INI_FA, FIN, 24, {"resets": {}, "congelamientos": [("2026-08-10 07:00", 27, meds_fa), ("2026-07-18 21:00", 60, ["RECTIFICADOR_2"])]})
    df_fa = df_fa[df_fa["t"] >= INI_FA + pd.Timedelta(hours=19)].reset_index(drop=True)

    pais = cfg["calendario"]["pais_festivos"]
    out = {}
    for planta, df, meds in (("RC", df_rc, meds_rc), ("F&A", df_fa, meds_fa)):
        hora, resumen, cong, _, rachas = ec.procesar_planta(df, planta, meds, cal, k, rac, pais)
        eh, et = ec.tablas_energia(hora)
        ec.actualizar_tabla("energia_hora", eh, planta, ["hora_inicio", "medidor"])
        ec.actualizar_tabla("energia_turno", et, planta, ["fecha_turno", "turno", "planta", "medidor"])
        ec.actualizar_tabla("rachas_constantes_energia", rachas, planta, ["inicio", "medidor"])
        ec.actualizar_tabla("cobertura_energia_mensual", ec.tabla_cobertura_mensual(hora), planta, ["mes", "medidor"])
        suf = "rc" if planta == "RC" else "fa"
        resumen.to_csv(CLEAN / f"calidad_energia_{suf}.csv", index=False)
        if len(cong):
            cong.to_csv(CLEAN / f"congelamientos_energia_{suf}.csv", index=False)
        out[planta] = hora
    fase2(salida, cfg, rng, prod, out, modelos, pais)
    return salida


# ---------------------------------------------------------------------------------------------- fase 2
def _silencio(ruta):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(ruta), run_name="__main__")


def _serie_mensual(rng, meses, base, amp, tendencia):
    n = len(meses)
    estacion = 1 + amp * np.sin(np.arange(n) / 12 * 2 * np.pi + rng.uniform(0, 6))
    return base * estacion * (1 + tendencia * np.arange(n) / n) * rng.normal(1, 0.04, n)


def fase2(salida, cfg, rng, prod, hora, modelos, pais):
    from src.comun.config import tabla_mapa_procesos
    CLEAN = salida / "data" / "clean"
    mes_ini = lambda a, b: pd.date_range(a, b, freq="MS")  # noqa: E731

    # --- producción del ERP y mapa de procesos
    pt = prod.copy()
    pt["fecha_turno"] = pt["fecha_turno"].dt.date
    pt.sort_values(["fecha_turno", "turno", "linea_erp"]).to_csv(CLEAN / "produccion_turno.csv", index=False)
    cp = pt.groupby(["planta", "linea_erp"]).agg(transacciones=("n_transacciones", "sum"), cantidad_neta=("cantidad", "sum")).reset_index()
    cp["reversos"], cp["fecha_ajustada"], cp["sin_categoria"] = 0, 0, 0
    cp["cantidad_neta"] = cp["cantidad_neta"].round(1)
    cp.to_csv(CLEAN / "calidad_produccion_erp.csv", index=False)
    tabla_mapa_procesos(cfg).to_csv(CLEAN / "mapa_procesos.csv", index=False)

    # --- series mensuales de las plantas (inventadas) y tarifa
    tarifa_m = mes_ini("2024-02-01", "2026-07-01")
    tar = np.clip(530 + np.cumsum(rng.normal(0, 7, len(tarifa_m))), 500, 575).round(2)
    tarifa = pd.Series(tar, index=tarifa_m)
    hr = hora["RC"]
    hr = hr[hr["medidor"].isin(["TRITURADO", "HORNO", "REFINO_1", "REFINO_2", "FILTRO_1", "FILTRO_2", "PTARI"])]
    scada_m = hr.assign(mes=hr["hora_inicio"].dt.to_period("M").dt.to_timestamp()).groupby("mes")["kwh_t"].sum()
    ref_t = (prod[prod["linea_erp"].isin(LINEAS["refinacion"])].assign(mes=lambda d: d["fecha_turno"].dt.to_period("M").dt.to_timestamp())
             .groupby("mes")["cantidad"].sum() / 1000).round(2)
    partes = []
    # RC: la energía de los 7 medidores es una fracción (~0.6) de lo que reporta la base; la producción equivalente es la refinación en toneladas
    meses = mes_ini("2017-10-01", "2026-06-01")
    kwh = _serie_mensual(rng, meses, 380000, 0.08, 0.2)
    peq = _serie_mensual(rng, meses, 1900, 0.10, 0.1)
    for m in meses:
        if m in scada_m.index and scada_m[m] > 0 and m in ref_t.index:
            kwh[meses.get_loc(m)] = scada_m[m] / rng.uniform(0.55, 0.78)
            peq[meses.get_loc(m)] = ref_t[m]
    partes.append(pd.DataFrame({"planta": "RC", "mes": meses, "kwh": kwh.round(0), "produccion_equivalente": peq.round(2)}))
    for planta, fin_m, kwh0, peq0, presup, evento in (("Ensamble", "2026-07-01", 250000, 80000, 2.0, True), ("OREC", "2026-06-01", 400000, 62000, 5.8, False),
                                                      ("F&A", "2026-07-01", 950000, 50000, 18.0, False)):
        meses = mes_ini("2019-10-01", fin_m)
        kwh = _serie_mensual(rng, meses, kwh0, 0.10, 0.15)
        peq = _serie_mensual(rng, meses, peq0, 0.12, 0.05)
        if evento and pd.Timestamp("2026-03-01") in meses:   # el indicador empeora aunque el consumo baje
            j = meses.get_loc(pd.Timestamp("2026-03-01"))
            kwh[j], peq[j] = kwh[j - 1] * 0.92, peq[j - 1] * 0.55
        if planta == "F&A":
            fa_m = hora["F&A"].assign(mes=lambda d: d["hora_inicio"].dt.to_period("M").dt.to_timestamp()).groupby("mes")["kwh_t"].sum()
            if pd.Timestamp("2026-07-01") in fa_m.index:
                kwh[meses.get_loc(pd.Timestamp("2026-07-01"))] = fa_m[pd.Timestamp("2026-07-01")] / 0.95
        partes.append(pd.DataFrame({"planta": planta, "mes": meses, "kwh": kwh.round(0), "produccion_equivalente": peq.round(2),
                                    "_presup": presup}))
    base = pd.concat(partes, ignore_index=True)
    base["kwh_por_eq"] = (base["kwh"] / base["produccion_equivalente"]).round(2)
    base["kwh_por_eq_presupuesto"] = np.where((base["mes"] >= "2025-10-01") & base["_presup"].notna(), base["_presup"], np.nan)
    base["costo_kwh_cop"] = np.where(base["planta"].ne("RC"), base["mes"].map(tarifa), np.nan)
    base["costo_total_cop"] = (base["kwh"] * base["costo_kwh_cop"]).round(2)
    base = base.drop(columns="_presup")
    base["mes"] = base["mes"].dt.date
    base.to_csv(CLEAN / "base_mensual_plantas.csv", index=False)
    pd.DataFrame({"mes": tarifa.index.date, "costo_kwh_cop": tarifa.values}).to_csv(CLEAN / "tarifa_kwh_mensual.csv", index=False)
    pres = base.dropna(subset=["kwh_por_eq_presupuesto"]).copy()
    mc = (pres.groupby("planta").agg(kwh_por_eq_meta=("kwh_por_eq_presupuesto", "first"), vigente_desde=("mes", "min"), vigente_hasta=("mes", "max"),
                                    meses=("mes", "size")).reset_index())
    mc["fuente"] = "Datos simulados (presupuesto inventado)"
    mc.to_csv(CLEAN / "metas_clarios.csv", index=False)
    meses = mes_ini("2017-10-01", "2026-06-01")
    gas = pd.DataFrame({"mes": meses.date, "m3": _serie_mensual(rng, meses, 140000, 0.12, 0.0).round(0), "produccion_equivalente": _serie_mensual(rng, meses, 1900, 0.1, 0.1).round(2)})
    gas["m3_por_eq"] = (gas["m3"] / gas["produccion_equivalente"]).round(2)
    gas["costo_m3_cop"] = np.where(meses >= "2025-10-01", np.where(meses >= "2026-01-01", 1799.4, 1681.7), np.nan)
    gas["costo_total_cop"] = (gas["m3"] * gas["costo_m3_cop"]).round(2)
    gas.to_csv(CLEAN / "base_mensual_gas_rc.csv", index=False)

    # --- gas diario del SCADA (60 días)
    dias = pd.date_range("2026-08-02", "2026-09-30")
    patron = np.array([760, 760, 730, 930, 890, 980, 1390])
    m3 = patron[dias.dayofweek] * rng.normal(1, 0.25, len(dias)).clip(0.2)
    calidad = np.array(["ok"] * len(dias), dtype=object)
    for d in ("2026-08-03", "2026-08-04", "2026-08-05"):
        calidad[list(dias).index(pd.Timestamp(d))] = "estimado"
    for d in ("2026-08-11", "2026-08-30", "2026-09-01", "2026-09-07"):
        calidad[list(dias).index(pd.Timestamp(d))] = "reinicio"
    pd.DataFrame({"fecha": dias.date, "m3": m3.round(1), "calidad": calidad}).to_csv(CLEAN / "gas_dia.csv", index=False)

    # --- tablas de modelado: el mismo script que con los datos reales
    for sub in ("energia_hora", "energia_turno"):
        assert (CLEAN / f"{sub}.csv").exists()
    _silencio(salida / "src" / "datos" / "03_dataset_modelo.py")
    dd = pd.read_csv(CLEAN / "dataset_modelo_dia.csv", parse_dates=["fecha"])
    g = pd.read_csv(CLEAN / "gas_dia.csv", parse_dates=["fecha"])
    pv = dd[dd["proceso_modelo"].isin(["horno", "refinacion"])].pivot_table(index="fecha", columns="proceso_modelo", values="produccion")
    pv.columns = [f"produccion_{c}_kg" for c in pv.columns]
    mg = g.merge(pv.reset_index(), on="fecha", how="left")
    mg["dia_semana"] = mg["fecha"].dt.dayofweek
    mg["es_fin_semana"] = (mg["dia_semana"] >= 5).astype(int)
    fest = holidays.country_holidays(pais, years=[2026])
    mg["es_festivo"] = mg["fecha"].dt.date.map(lambda d: int(d in fest))
    mg["calidad_ok"] = (mg["calidad"] == "ok").astype(int)
    mg["fecha"] = mg["fecha"].dt.date
    mg.round(1).to_csv(CLEAN / "dataset_modelo_gas_dia.csv", index=False)

    # --- validación contra la base (misma lógica de 01_energia_scada.py y 05_energia_fa.py)
    base_rc = base[base["planta"] == "RC"].assign(mes=lambda d: pd.to_datetime(d["mes"]).dt.to_period("M")).set_index("mes")["kwh"]
    hr2 = hr.assign(mes=hr["hora_inicio"].dt.to_period("M"))
    pm = hr2.groupby(["mes", "medidor"]).agg(kwh=("kwh_t", "sum"), validas=("valida_total", "sum"), total=("valida_total", "size")).reset_index()
    pm["kwh_est"] = pm["kwh"] * pm["total"] / pm["validas"].replace(0, np.nan)
    mens = pm.groupby("mes").agg(kwh_scada_7_procesos=("kwh", "sum"), kwh_estimado_por_cobertura=("kwh_est", "sum"), horas_validas=("validas", "sum"), horas_total=("total", "sum"))
    mens["cobertura"] = (mens["horas_validas"] / mens["horas_total"]).round(3)
    est = hr2[hr2["calidad"] == "estimado"].groupby("mes").size()
    mens["horas_estimadas_por_congelamiento"] = est.reindex(mens.index).fillna(0).astype(int)
    mens["kwh_emcali_si_contador_en_wh"], mens["kwh_edif_admon_si_contador_en_wh"] = np.nan, np.nan
    mens["kwh_base_clarios"] = base_rc.reindex(mens.index)
    mens["ratio_scada_vs_base"] = (mens["kwh_scada_7_procesos"] / mens["kwh_base_clarios"]).round(3)
    mens["ratio_estimado_vs_base"] = (mens["kwh_estimado_por_cobertura"] / mens["kwh_base_clarios"]).round(3)
    posibles = 7 * 24 * pd.Series(mens.index.days_in_month, index=mens.index)
    mens["mes_completo"] = mens["horas_total"] >= posibles * cfg["calidad"]["cobertura_mes_completo"]
    mens.round(3).to_csv(CLEAN / "validacion_energia_rc_mensual.csv", index_label="mes")
    hf = hora["F&A"].assign(mes=lambda d: d["hora_inicio"].dt.to_period("M"))
    mf = hf.groupby("mes").agg(kwh_scada_3_rectificadores=("kwh_t", "sum"), horas_validas=("valida_total", "sum"), horas_total=("valida_total", "size"))
    mf["cobertura"] = (mf["horas_validas"] / mf["horas_total"]).round(3)
    bf = base[base["planta"] == "F&A"].assign(mes=lambda d: pd.to_datetime(d["mes"]).dt.to_period("M")).set_index("mes")["kwh"]
    mf = mf.join(bf.rename("kwh_base_clarios"))
    mf.round(3).to_csv(CLEAN / "validacion_energia_fa_mensual.csv", index_label="mes")

    # --- resultados del modelo (solo inferencia con los modelos ya entrenados), pronóstico, metas y plantas
    from src.modelos import run_modelo_v6 as v6
    dm = pd.read_csv(CLEAN / "dataset_modelo.csv", parse_dates=["fecha_turno"])
    dm = dm[dm["proceso_modelo"].isin(v6.PROCESOS_RC + [v6.PROCESO_FA])].copy()
    dm.loc[dm["proceso_modelo"] == v6.PROCESO_FA, "planta"] = "F&A"
    dm = dm.sort_values(["proceso_modelo", "fecha_turno", "turno"])
    res = v6.construir_resultados(dm[dm["calidad_ok"] == 1], modelos, CONFIANZA)
    cols = ["fecha_turno", "turno", "planta", "proceso_modelo", "kwh", "kwh_esperado", "exceso_kwh", "exceso_pct", "puntaje_anomalia", "es_anomalia",
            "severidad", "costo_exceso_cop", "confianza_modelo"]
    r = res[cols].rename(columns={"kwh": "kwh_real"}).copy()
    r[["exceso_kwh", "exceso_pct"]] = r[["exceso_kwh", "exceso_pct"]].round(2)
    r["costo_exceso_cop"] = r["costo_exceso_cop"].round(0)
    r[["kwh_real", "kwh_esperado"]] = r[["kwh_real", "kwh_esperado"]].round(3)
    r["fecha_turno"] = pd.to_datetime(r["fecha_turno"]).dt.date
    r.to_csv(CLEAN / "resultados_modelo.csv", index=False)
    for script in ("run_pronostico_v2.py", "run_ensamble_orec.py"):
        _silencio(salida / "src" / "modelos" / script)
    _silencio(salida / "src" / "datos" / "04_eda_rc.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True, help="carpeta de salida (ruta corta; se borra y se recrea)")
    a = ap.parse_args()
    s = main(a.salida)
    tablas = sorted(p.stem for p in (s / "data" / "clean").glob("*.csv"))
    print(f"listo: {len(tablas)} tablas en {s / 'data' / 'clean'}")
    print(tablas)
