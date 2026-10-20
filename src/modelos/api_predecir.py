"""api_predecir.py — fachada simple y reutilizable para el dashboard (Joshua).

    from src.modelos.api_predecir import predecir
    predecir("horno", 120000, planta="RC")   # -> dict con kwh_esperado e intervalo

No entrena nada: lee `data/interim/modelos.pkl` (lo genera run_modelo_v6.py; `python src/modelos/run_pipeline.py` lo deja listo).
"""
from __future__ import annotations

from src.modelos.modelo_esperado_api import cargar_modelos, predecir  # noqa: F401

__all__ = ["predecir", "cargar_modelos"]
