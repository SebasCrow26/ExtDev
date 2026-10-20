"""Paso 2 (Datos): producción del ERP por turno y línea.

Toma las transacciones RCT-WO (recepción por orden de trabajo = reporte de producción), las asigna a un
turno y una línea de producción, y deja la producción neta (descontando reversos) en data/clean.

Uso (desde la raíz del repositorio):  python src/datos/02_produccion_erp.py

Salidas en data/clean: produccion_turno, calidad_produccion_erp

Reglas:
  - Fecha-hora de la transacción = Fecha + Tiempo. El ERP pone como "Fecha Efectiva" el día siguiente a las
    transacciones de la noche (22:00 en adelante), así que NO se usa la fecha efectiva.
  - Si la transacción se registró 2 o más días antes o después de su fecha efectiva (registro tardío), se usa la
    fecha efectiva con la hora del registro y se cuenta en `n_fecha_ajustada`.
  - Cantidad neta = suma de cantidades (los reversos son transacciones con cantidad negativa).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, lineas_a_proceso  # noqa: E402
from src.comun.turnos import turno_y_fecha  # noqa: E402

RAW = RAIZ / "data" / "raw"
CLEAN = RAIZ / "data" / "clean"

COLUMNAS = ["Fecha Efectiva", "Fecha", "Tiempo", "Almac", "Número Artículo", "Línea de productos",
            "Cantidad del Cambio", "Unidad de medida", "Campo Equs", "Línea Producción", "Tipo Transacción"]
CFG = cargar_config()
PROCESO_MODELO = lineas_a_proceso(CFG)
UNIDADES = CFG["unidades"]["erp_a_normalizada"]
PREFIJOS_PLANTA = [tuple(p) for p in CFG["produccion"]["prefijos_planta"]]
DIAS_DESFASE = CFG["produccion"]["dias_desfase_fecha_efectiva"]


def planta_de(linea, mapa):
    if linea in mapa:
        return mapa[linea]
    for pref, planta in PREFIJOS_PLANTA:
        if linea.startswith(pref):
            return planta
    return "Sin_planta"


def main():
    CLEAN.mkdir(parents=True, exist_ok=True)
    df = pd.read_excel(RAW / "Calculo de equivalente- Explorar transacciones por art.xlsx", sheet_name="Datos",
                       usecols=COLUMNAS, engine="calamine")
    print(f"Transacciones leídas: {len(df):,}. Tipos: {df['Tipo Transacción'].unique().tolist()}")

    # el archivo de Clarios trae una primera columna vacía: se descartan las columnas sin datos y se exigen las 3 esperadas
    mapa = pd.read_excel(RAW / "Calculo de equivalente- Comparativo lineas.xlsx", engine="calamine").dropna(how="all").dropna(axis=1, how="all")
    if mapa.shape[1] != 3 or not str(mapa.columns[0]).strip().lower().startswith("planta"):
        raise SystemExit(f"Formato inesperado del mapa de líneas: columnas {list(mapa.columns)}")
    mapa.columns = ["planta", "proceso", "linea"]
    mapa["planta"] = mapa["planta"].astype(str).str.strip()
    mapa["linea"] = mapa["linea"].astype(str).str.strip().str.upper()
    mapa_planta = dict(zip(mapa["linea"], mapa["planta"].astype(str).str.strip()))

    df["linea_erp"] = df["Línea Producción"].fillna("SIN_LINEA").astype(str).str.strip().str.upper()
    df["categoria_equs"] = df["Campo Equs"].fillna("SIN_CATEGORIA").astype(str).str.strip().replace({"N/A": "SIN_CATEGORIA", "": "SIN_CATEGORIA"})
    df["unidad"] = df["Unidad de medida"].astype(str).str.strip().str.upper().map(UNIDADES).fillna("otra")

    dif = (df["Fecha"] - df["Fecha Efectiva"]).dt.days.abs()
    df["fecha_ajustada"] = dif >= DIAS_DESFASE
    base = df["Fecha"].where(~df["fecha_ajustada"], df["Fecha Efectiva"])
    df["ts"] = base.dt.normalize() + pd.to_timedelta(df["Tiempo"].astype(str) + ":00")
    df["turno"], df["fecha_turno"] = turno_y_fecha(df["ts"])

    df["planta"] = [planta_de(l, mapa_planta) for l in df["linea_erp"]]
    df["proceso_modelo"] = df["linea_erp"].map(PROCESO_MODELO).fillna("")
    df["reverso"] = df["Cantidad del Cambio"] < 0

    pt = (df.groupby(["fecha_turno", "turno", "planta", "linea_erp", "proceso_modelo", "categoria_equs", "unidad"], dropna=False)
          .agg(cantidad=("Cantidad del Cambio", "sum"), n_transacciones=("Cantidad del Cambio", "size"),
               n_fecha_ajustada=("fecha_ajustada", "sum")).reset_index())
    pt["cantidad"] = pt["cantidad"].round(3)
    pt["fecha_turno"] = pt["fecha_turno"].dt.date
    pt = pt[["fecha_turno", "turno", "planta", "linea_erp", "proceso_modelo", "categoria_equs", "cantidad", "unidad",
             "n_transacciones", "n_fecha_ajustada"]].sort_values(["fecha_turno", "turno", "planta", "linea_erp"])
    pt.to_csv(CLEAN / "produccion_turno.csv", index=False)

    q = (df.groupby(["planta", "linea_erp"]).agg(
        transacciones=("reverso", "size"), cantidad_neta=("Cantidad del Cambio", "sum"),
        reversos=("reverso", "sum"), fecha_ajustada=("fecha_ajustada", "sum"),
        sin_categoria=("categoria_equs", lambda s: int((s == "SIN_CATEGORIA").sum()))).reset_index())
    q["cantidad_neta"] = q["cantidad_neta"].round(1)
    q.sort_values(["planta", "transacciones"], ascending=[True, False]).to_csv(CLEAN / "calidad_produccion_erp.csv", index=False)

    print(f"\nTransacciones con fecha ajustada (registro tardío): {int(df['fecha_ajustada'].sum()):,} "
          f"({100 * df['fecha_ajustada'].mean():.1f}%). Reversos (cantidad negativa): {int(df['reverso'].sum())}")
    print(f"Sin línea de producción: {(df['linea_erp'] == 'SIN_LINEA').sum():,}. Sin categoría de equivalente: {(df['categoria_equs'] == 'SIN_CATEGORIA').sum():,}")
    print("\nLíneas de RC y F&A (producción neta en el año fiscal):")
    sel = q[q["planta"].isin(["RC", "F&A"])].sort_values(["planta", "transacciones"], ascending=[True, False])
    print(sel.to_string(index=False))
    print(f"\nproduccion_turno: {len(pt):,} filas. Rango de fecha_turno: {pt['fecha_turno'].min()} a {pt['fecha_turno'].max()}")


if __name__ == "__main__":
    main()
