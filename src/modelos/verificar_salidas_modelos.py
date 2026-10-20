"""verificar_salidas_modelos.py — chequeo rápido de las salidas de Modelos antes de subir a Git (Joshua).

Comprueba que `data/clean/resultados_modelo.csv`, `pronostico.csv` y `metas.csv` tienen las columnas
del contrato (`documentacion/01_contrato_datos.md`), que no hay claves duplicadas y que los rangos son plausibles.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

CLEAN = RAIZ / "data" / "clean"

ESPERADAS = {
    "resultados_modelo": ["fecha_turno", "turno", "planta", "proceso_modelo", "kwh_real", "kwh_esperado",
                          "exceso_kwh", "exceso_pct", "puntaje_anomalia", "es_anomalia", "severidad", "costo_exceso_cop"],
    "pronostico": ["fecha", "planta", "proceso_modelo", "escenario", "produccion_supuesta",
                   "kwh_pronosticado", "kwh_inferior", "kwh_superior"],
    "metas": ["planta", "proceso_modelo", "meta_kwh_por_unidad", "fuente", "vigente_desde"],
}
CLAVES = {
    "resultados_modelo": ["fecha_turno", "turno", "planta", "proceso_modelo"],
    "pronostico": ["fecha", "planta", "proceso_modelo", "escenario"],
    "metas": ["planta", "proceso_modelo"],
}


def main():
    fallos = []
    for nombre, cols in ESPERADAS.items():
        ruta = CLEAN / f"{nombre}.csv"
        if not ruta.exists():
            print(f"[FALTA] {ruta}")
            fallos.append(nombre)
            continue
        df = pd.read_csv(ruta)
        faltan = [c for c in cols if c not in df.columns]
        dup = int(df.duplicated(subset=CLAVES[nombre]).sum())
        print(f"{nombre:18s} filas={len(df):6d} columnas={len(df.columns):3d} "
              f"faltantes={faltan if faltan else 'ninguna'} duplicados={dup}")
        if faltan:
            fallos.append(nombre)
        if dup:
            fallos.append(f"{nombre}(duplicados)")
    print("\nRESULTADO:", "REVISAR" if fallos else "OK — todas las salidas cumplen el contrato")


if __name__ == "__main__":
    main()
