"""run_anomalias_v2.py — igual que run_anomalias.py pero usando tablas Markdown manuales
(sin depender de `tabulate`).
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
from src.modelos.comun_modelos import PROCESOS_RC, PROCESO_FA, z_robusto  # noqa: E402

INTERIM = RAIZ / "data" / "interim"
DOCS = RAIZ / "documentacion" / "modelos"
CLEAN = RAIZ / "data" / "clean"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def isolation_forest(tab, contaminacion=0.02):
    try:
        from sklearn.ensemble import IsolationForest
        cols = ["produccion", "kwh_esperado", "exceso_kwh"]
        X = tab[cols].fillna(0).to_numpy()
        iso = IsolationForest(n_estimators=300, contamination=contaminacion, random_state=0)
        pred = iso.fit_predict(X)
        return (pred == -1).astype(int)
    except Exception:
        return np.zeros(len(tab), dtype=int)


def main():
    res = pd.read_csv(CLEAN / "resultados_modelo.csv", parse_dates=["fecha_turno"])
    dm = leer_tabla("dataset_modelo")[["fecha_turno", "turno", "planta", "proceso_modelo", "produccion", "es_fin_semana", "es_festivo"]]
    res = res.merge(dm, on=["fecha_turno", "turno", "planta", "proceso_modelo"], how="left")

    lineas = ["# 04 · Anomalías y severidad (Joshua)", "",
             "Residuos robustos (mediana + MAD) por proceso sobre `resultados_modelo`, "
             "más IsolationForest (2% de contaminación) sobre el perfil [producción, esperado, exceso]. "
             "Severidad por **costo del exceso** (no por porcentaje).", ""]

    casos = []
    for proc, g in res.groupby("proceso_modelo"):
        g = g.copy()
        g["z_robusto"] = z_robusto(g["kwh_real"] - g["kwh_esperado"].to_numpy())
        g["iso"] = isolation_forest(g)
        g["es_anomalia_final"] = ((g["puntaje_anomalia"] >= 0.5) | (g["iso"] == 1)).astype(int)
        casos.append(g)
    res = pd.concat(casos, ignore_index=True)

    orden = {"alta": 0, "media": 1, "baja": 2}
    res["_o"] = res["severidad"].map(orden)
    top = res.sort_values(["_o", "costo_exceso_cop"], ascending=[True, False]).head(25)

    lineas += ["## Top 25 casos por severidad y costo del exceso", "",
               "| fecha_turno | turno | planta | proceso | kwh_real | kwh_esperado | exceso_kwh | costo COP | puntaje | z_robusto | iso | severidad |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in top.iterrows():
        lineas.append(f"| {r['fecha_turno'].date()} | {int(r['turno'])} | {r['planta']} | {r['proceso_modelo']} | "
                      f"{r['kwh_real']:.0f} | {r['kwh_esperado']:.0f} | {r['exceso_kwh']:.0f} | {r['costo_exceso_cop']:.0f} | "
                      f"{r['puntaje_anomalia']} | {r['z_robusto']:.1f} | {int(r['iso'])} | {r['severidad']} |")

    resumen = res.groupby(["proceso_modelo", "severidad"]).size().unstack(fill_value=0).reset_index()
    lineas += ["", "## Conteo por proceso y severidad", "", md_tabla(resumen), "",
               "Caso real documentado (documentacion/09): **triturado funcionando en domingo** (23 y 30 ago, 6 sep 2026 "
               "entre otros) con 450–888 kWh frente a un típico de ~19: es el caso que el dashboard debe alertar "
               "como «consumo en turno no operativo».", ""]

    INTERIM.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    with open(INTERIM / "anomalias.pkl", "wb") as f:
        pickle.dump(res, f)
    (DOCS / "04_anomalias.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escritos {DOCS / '04_anomalias.md'} y {INTERIM / 'anomalias.pkl'} ({len(res)} filas)")
    print("\n".join(lineas[:35]))


if __name__ == "__main__":
    main()
