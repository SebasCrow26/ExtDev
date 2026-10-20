"""test_modelos.py — prueba básica de la API `predecir()` (Joshua).
"""
from __future__ import annotations

import pickle
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from src.modelos.modelo_esperado_api import cargar_modelos, predecir  # noqa: E402


class TestPredecir(unittest.TestCase):
    def test_cargar_modelos(self):
        modelos = cargar_modelos()
        self.assertIn("dia|horno", modelos)
        self.assertIn("turno|triturado", modelos)

    def test_predecir_devuelve_dict(self):
        out = predecir("horno", 100000, planta="RC", nivel="dia", dia_semana=0)
        self.assertIsInstance(out, dict)
        self.assertIn("kwh_esperado", out)
        self.assertGreater(out["kwh_esperado"], 0)
        self.assertGreaterEqual(out["kwh_superior"], out["kwh_inferior"])

    def test_predecir_proceso_invalido(self):
        with self.assertRaises(ValueError):
            predecir("no_existe", 100)


if __name__ == "__main__":
    unittest.main()
