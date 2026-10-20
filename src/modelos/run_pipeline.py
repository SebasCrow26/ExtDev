"""run_pipeline.py — orquestador único de la pipeline de Modelos (Joshua).

Ejecuta en orden:
1. run_modelo_v6.py        -> resultados_modelo.csv + modelos.pkl + documentacion/modelos/03_modelo_esperado.md
2. run_anomalias_v2.py     -> documentacion/modelos/04_anomalias.md + data/interim/anomalias.pkl
3. run_pronostico_v2.py    -> pronostico.csv, metas.csv + documentacion/modelos/05_pronostico_y_ahorro.md
4. run_evaluar.py          -> documentacion/modelos/evaluar.md

`run_linea_base.py` (línea base) se ejecuta antes si no existe `data/interim/linea_base.pkl`.

Uso:  python src/modelos/run_pipeline.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INTERIM = RAIZ / "data" / "interim"

PASOS = [
    ("src/modelos/run_modelo_v6.py", "Modelo de consumo esperado (Huber/GBR por celda) y resultados_modelo"),
    ("src/modelos/run_anomalias_v2.py", "Anomalías (MAD + IsolationForest) y severidad"),
    ("src/modelos/run_pronostico_v2.py", "Pronóstico, metas y ahorro potencial"),
    ("src/modelos/run_evaluar.py", "Reporte consolidado de métricas"),
]


def _ejecutar(script: str, desc: str, i: int, n: int) -> None:
    t0 = time.time()
    print(f"[{i}/{n}] {desc} ({script})...", flush=True)
    r = subprocess.run([sys.executable, "-W", "ignore", str(RAIZ / script)], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode != 0:
        print(r.stdout[-6000:], r.stderr[-3000:])
        sys.exit(f"Falló {script} (código {r.returncode})")
    print(f"      listo en {time.time() - t0:.0f} s")


def main():
    inicio = time.time()
    n = len(PASOS)
    if not (INTERIM / "linea_base.pkl").exists():
        _ejecutar("src/modelos/run_linea_base.py", "Línea base (proceso × turno × día)", 0, n + 1)
    for i, (script, desc) in enumerate(PASOS, 1):
        _ejecutar(script, desc, i, n)
    print(f"\nPipeline de Modelos completa en {time.time() - inicio:.0f} s.")
    print("Tablas generadas en data/clean/: resultados_modelo.csv, pronostico.csv, metas.csv")
    print("Reportes en documentacion/modelos/: 01_exploracion.md, 02_linea_base.md, 03_modelo_esperado.md, "
          "04_anomalias.md, 05_pronostico_y_ahorro.md, evaluar.md")


if __name__ == "__main__":
    main()
