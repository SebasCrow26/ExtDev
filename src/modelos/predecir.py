"""predecir.py — fachada simple y reutilizable para el dashboard (Joshua).

    from src.modelos.predecir import predecir
    predecir("horno", 120000, planta="RC")   # -> dict con kwh_esperado e intervalo

No entrena nada: lee `data/interim/modelos.pkl` (lo genera run_modelo_v6.py; `python src/modelos/run_pipeline.py` lo deja listo).
Si el pickle no existe, avisa con un error claro.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.modelos.modelo_esperado_api import predecir, cargar_modelos  # noqa: E402,F401

__all__ = ["predecir", "cargar_modelos"]
