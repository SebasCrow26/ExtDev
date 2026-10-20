"""evaluar.py — reporte de métricas del frente de Modelos (Joshua).

Consolida las métricas de la línea base (02) y del modelo elegido (03) en la prueba
jul–sep 2026, por proceso y nivel. Es el "reporte corto de métricas" del checklist.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

INTERIM = RAIZ / "data" / "interim"
DOCS = RAIZ / "documentacion" / "modelos"


def md_tabla(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |",
           "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(out)


def main():
    with open(INTERIM / "linea_base.pkl", "rb") as f:
        lb = pickle.load(f)

    filas = []
    for nivel, proc, me_ent, me_pru in lb.get("metricas", []):
        filas.append({"nivel": nivel, "proceso": proc, "modelo": "linea_base",
                      "MAE_ent": me_ent["mae"], "WAPE_ent": me_ent["wape"], "R2_ent": me_ent["r2"],
                      "MAE_pru": me_pru["mae"], "WAPE_pru": me_pru["wape"], "R2_pru": me_pru["r2"]})

    lineas = ["# evaluar · reporte de métricas (Joshua)", "",
             "Split temporal de `config/config.yaml`: entrenamiento **oct 2025 – jun 2026**, "
             "prueba **jul – sep 2026**. Métricas: MAE (kWh), WAPE (%) y R² clásico (1 − SS_res/SS_tot, "
             "contra la media real de la prueba).", "",
             "## Línea base (02) por proceso y nivel", "",
             md_tabla(pd.DataFrame(filas)) if filas else "_sin datos_", "",
             "## Modelo Huber/GBR vs línea base (detalle en `03_modelo_esperado.md`)", "",
             "El modelo elegido por celda (proceso × nivel) se documenta con `✓` en `03_modelo_esperado.md`. "
             "Cuando ningún modelo supera la línea base, se recomienda dejar la línea base para ese proceso "
             "(riesgo aceptado en `documentacion/00_plan_de_trabajo.md`, «Plan B»).", "",
             "## Métricas del frente (resumen para Gabriel)", "",
             "- MAE, WAPE y R² por proceso y nivel (turno/día/semana) en la prueba.",
             "- % de turnos descartados por calidad de datos (cobertura < 0.75 o `calidad_ok = 0`).",
             "- Comparación explícita contra la línea base.",
             "- Caso real de desviación detectada (triturado en domingo: `04_anomalias.md`).", ""]

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "evaluar.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escrito {DOCS / 'evaluar.md'}")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
