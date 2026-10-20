"""Pruebas de lo que se corrigió en la auditoría final del frente de Modelos: calendario y rezagos del pronóstico,
exceso neto, confianza del modelo y que las tablas entregadas cumplan el horizonte configurado.

No necesitan los modelos entrenados (data/interim): usan datos sintéticos y las tablas de data/clean.
Uso (desde la raíz del repositorio):  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config  # noqa: E402
from src.modelos.modelo_esperado_api import features  # noqa: E402
from src.modelos.run_modelo_v6 import confianza  # noqa: E402
from src.modelos.run_pronostico_v2 import agregar_dias_futuros, produccion_por_dia, resumen_exceso  # noqa: E402


def serie_real(dias=14, hasta="2026-09-30"):
    fechas = pd.date_range(end=hasta, periods=dias, freq="D")
    return pd.DataFrame({"fecha_turno": fechas, "planta": "RC", "proceso_modelo": "horno", "kwh": 1000.0,
                         "produccion": np.arange(1, dias + 1) * 100.0, "dia_semana": fechas.dayofweek,
                         "es_fin_semana": (fechas.dayofweek >= 5).astype(int), "es_festivo": 0})


class PruebasPronostico(unittest.TestCase):
    def test_la_fila_futura_trae_su_propio_calendario(self):
        tab = serie_real()  # el último día real es miércoles 30 de septiembre
        self.assertEqual(tab["fecha_turno"].iloc[-1].dayofweek, 2)
        fechas = [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-03")]  # jueves y sábado
        serie = agregar_dias_futuros(tab, fechas, [111.0, 222.0], festivos={pd.Timestamp("2026-10-03").date()})
        f = features(serie, "dia").iloc[-2:]
        self.assertEqual(f["dia_3"].tolist(), [1.0, 0.0])  # jueves
        self.assertEqual(f["dia_5"].tolist(), [0.0, 1.0])  # sábado
        self.assertEqual(f["es_fin_semana"].tolist(), [0.0, 1.0])
        self.assertEqual(f["es_festivo"].tolist(), [0.0, 1.0])

    def test_los_rezagos_usan_la_produccion_previa_real_o_supuesta(self):
        tab = serie_real()
        ultima_real = float(tab["produccion"].iloc[-1])
        penultima = float(tab["produccion"].iloc[-2])
        serie = agregar_dias_futuros(tab, [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")], [111.0, 222.0], festivos=set())
        f = features(serie, "dia").iloc[-2:]
        self.assertEqual(f["produccion_t1"].tolist(), [ultima_real, 111.0])
        self.assertEqual(f["produccion_t2"].tolist(), [penultima, ultima_real])  # antes quedaban en 0

    def test_produccion_supuesta_es_la_del_mismo_dia_de_la_semana(self):
        tab = serie_real(dias=28)
        jueves = tab[tab["fecha_turno"].dt.dayofweek == 3]["produccion"].mean()
        domingo = tab[tab["fecha_turno"].dt.dayofweek == 6]["produccion"].mean()
        p = produccion_por_dia(tab, [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-04")], semanas=4)
        self.assertAlmostEqual(p[0], jueves)
        self.assertAlmostEqual(p[1], domingo)
        self.assertNotAlmostEqual(p[0], p[1])


class PruebasExcesoNeto(unittest.TestCase):
    def test_neto_es_exceso_menos_defecto(self):
        res = pd.DataFrame({"fecha_turno": ["2026-01-01", "2026-01-02", "2026-08-01"], "proceso_modelo": ["a", "a", "b"],
                            "kwh_real": [110.0, 96.0, 103.0], "exceso_kwh": [10.0, -4.0, 3.0]})
        ex = resumen_exceso(res, fin_entrenamiento="2026-06-30")
        self.assertEqual((ex["pos"], ex["neg"], ex["neto"]), (13.0, -4.0, 9.0))
        self.assertEqual(ex["neto_entrenamiento"], 6.0)
        self.assertEqual(ex["neto_prueba"], 3.0)
        self.assertEqual(ex["por_proceso"].loc["a", "neto"], 6.0)

    def test_un_modelo_con_error_simetrico_no_genera_ahorro(self):
        e = np.array([50.0, -50.0, 30.0, -30.0])
        res = pd.DataFrame({"fecha_turno": "2026-01-01", "proceso_modelo": "a", "kwh_real": 1000.0, "exceso_kwh": e})
        ex = resumen_exceso(res)
        self.assertGreater(ex["pos"], 0)
        self.assertEqual(ex["neto"], 0.0)  # el exceso bruto (80) no es ahorro: el defecto lo compensa


class PruebasConfianza(unittest.TestCase):
    def test_reglas(self):
        self.assertEqual(confianza(0.63, -0.06), "alta")      # supera la línea base con R² alto
        self.assertEqual(confianza(0.21, 0.23), "media")      # igual a la línea base y R² positivo
        self.assertEqual(confianza(0.26, 0.31), "media")
        self.assertEqual(confianza(-0.26, -0.04), "baja")     # R² negativo y peor que la línea base
        self.assertEqual(confianza(float("nan"), 0.2), "baja")
        self.assertEqual(confianza(0.7, float("nan")), "alta")


class PruebasFachadaPredecir(unittest.TestCase):
    def test_las_dos_fachadas_se_importan_como_estan_documentadas(self):
        import importlib
        for nombre in ("src.modelos.predecir", "src.modelos.api_predecir"):
            m = importlib.import_module(nombre)  # antes `predecir` fallaba con ModuleNotFoundError
            self.assertTrue(callable(m.predecir), nombre)
            self.assertTrue(callable(m.cargar_modelos), nombre)

    def test_sin_modelos_entrenados_el_error_dice_que_hacer(self):
        import tempfile
        from unittest import mock
        import src.modelos.modelo_esperado_api as api
        with tempfile.TemporaryDirectory() as vacio, mock.patch.object(api, "INTERIM", Path(vacio)), mock.patch.object(api, "MODELOS", Path(vacio)):
            with self.assertRaises(FileNotFoundError) as e:
                api.cargar_modelos()
        self.assertIn("modelos/modelos.pkl", str(e.exception))


@unittest.skipUnless((RAIZ / "modelos" / "modelos.pkl").exists(), "falta modelos/modelos.pkl")
class PruebasPredecirCoincideConLasTablas(unittest.TestCase):
    def test_predecir_da_lo_mismo_que_pronostico_csv(self):
        from src.modelos.predecir import predecir
        p = pd.read_csv(RAIZ / "datos_simulados" / "pronostico.csv")
        dd = pd.read_csv(RAIZ / "datos_simulados" / "dataset_modelo_dia.csv", parse_dates=["fecha"])
        primera = p["fecha"].min()
        for _, f in p[(p["escenario"] == "base") & (p["fecha"] == primera)].iterrows():
            d = dd[(dd["proceso_modelo"] == f["proceso_modelo"]) & (dd["calidad_ok"] == 1)].sort_values("fecha")
            r = predecir(f["proceso_modelo"], float(f["produccion_supuesta"]), nivel="dia", fecha=primera,
                         produccion_t1=float(d["produccion"].iloc[-1]), produccion_t2=float(d["produccion"].iloc[-2]))
            self.assertAlmostEqual(r["kwh_esperado"], f["kwh_pronosticado"], delta=0.2, msg=f["proceso_modelo"])
            self.assertAlmostEqual(r["kwh_inferior"], f["kwh_inferior"], delta=0.2, msg=f["proceso_modelo"])
            self.assertAlmostEqual(r["kwh_superior"], f["kwh_superior"], delta=0.2, msg=f["proceso_modelo"])

    def test_el_calendario_cambia_la_prediccion(self):
        from src.modelos.predecir import predecir
        jueves = predecir("triturado", 50000, nivel="dia", fecha="2026-10-01")["kwh_esperado"]
        domingo = predecir("triturado", 50000, nivel="dia", fecha="2026-10-04")["kwh_esperado"]
        self.assertNotAlmostEqual(jueves, domingo, places=1)


class PruebasTablasEntregadas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = pd.read_csv(RAIZ / "datos_simulados" / "pronostico.csv", parse_dates=["fecha"])
        cls.r = pd.read_csv(RAIZ / "datos_simulados" / "resultados_modelo.csv")
        cls.h = int(cargar_config()["modelos"]["horizonte_pronostico_dias"])

    def test_pronostico_tiene_el_horizonte_configurado_sin_huecos(self):
        for (proc, esc), g in self.p.groupby(["proceso_modelo", "escenario"]):
            self.assertEqual(len(g), self.h, (proc, esc))
            self.assertEqual(g["fecha"].diff().dropna().dt.days.unique().tolist(), [1], (proc, esc))

    def test_pronostico_no_es_negativo_y_el_intervalo_es_coherente(self):
        self.assertTrue((self.p[["kwh_pronosticado", "kwh_inferior", "kwh_superior"]] >= 0).all().all())
        self.assertTrue(((self.p.kwh_inferior <= self.p.kwh_pronosticado + 0.01) & (self.p.kwh_pronosticado <= self.p.kwh_superior + 0.01)).all())

    def test_los_escenarios_ordenan_la_produccion_supuesta(self):
        w = self.p.pivot_table(index=["proceso_modelo", "fecha"], columns="escenario", values="produccion_supuesta")
        self.assertTrue(((w["bajo"] <= w["base"] + 0.1) & (w["base"] <= w["alto"] + 0.1)).all())

    def test_cada_proceso_tiene_una_sola_confianza_valida(self):
        g = self.r.groupby("proceso_modelo")["confianza_modelo"].nunique()
        self.assertTrue((g == 1).all())
        self.assertTrue(set(self.r["confianza_modelo"]) <= {"alta", "media", "baja"})


if __name__ == "__main__":
    unittest.main()
