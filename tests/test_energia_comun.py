"""Pruebas de la lógica de limpieza de contadores del SCADA (src/datos/energia_comun.py) con datos sintéticos.

Cada prueba construye contadores acumulados de los que se conoce la respuesta correcta (consumo constante, reinicio, salto,
hueco, congelamiento) y comprueba la calidad asignada, la conservación de la energía y que los parámetros de config.yaml
cambian de verdad el resultado.

Uso (desde la raíz del repositorio):  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from src.comun.config import cargar_config, catalogo, supuestos_en_uso  # noqa: E402
from src.comun.turnos import horas_por_turno  # noqa: E402
from src.datos.energia_comun import procesar_medidor, procesar_planta  # noqa: E402

CAL = cargar_config()["calidad"]
K = cargar_config()["unidades"]["contador_energia_a_kwh"]
WH_POR_HORA = 1000.0  # 1 kWh por hora
INICIO = pd.Timestamp("2026-01-05 00:00")


def serie(horas, incrementos=None):
    """Contador acumulado con lecturas cada hora en punto. `incrementos`: lista de Wh por intervalo (por defecto 1000)."""
    inc = incrementos if incrementos is not None else [WH_POR_HORA] * (horas - 1)
    valores = 100000.0 + np.concatenate([[0.0], np.cumsum(inc)])
    return pd.Series(pd.date_range(INICIO, periods=horas, freq="h")), pd.Series(valores)


def procesar(t, v, **kw):
    out, _ = procesar_medidor(t, v, kw.get("thr_x", CAL["umbral_salto_x_p99"]), kw.get("max_h", CAL["max_horas_interpolar"]),
                              kw.get("ventanas", []), kw.get("pct", CAL["percentil_salto"]), kw.get("hueco_h", CAL["umbral_hueco_interpolable_horas"]))
    return out


class PruebasLimpieza(unittest.TestCase):
    def test_consumo_constante_se_recupera_exacto(self):
        out = procesar(*serie(30))
        self.assertTrue((out["calidad"] == "ok").all())
        np.testing.assert_allclose(out["wh"], WH_POR_HORA)
        self.assertAlmostEqual(out["wh"].sum() * K, 29.0, places=6)

    def test_reinicio_del_contador_no_produce_consumo_negativo(self):
        t, v = serie(30)
        v.iloc[15:] -= 50000.0  # el contador baja
        out = procesar(t, v)
        self.assertIn("reinicio", set(out["calidad"]))
        self.assertTrue(out.loc[out["calidad"] == "reinicio", "wh"].isna().all())
        self.assertTrue((out["wh"].dropna() >= 0).all())

    def test_salto_de_golpe_se_marca_y_no_se_cuenta(self):
        # el umbral usa el percentil 99 de los incrementos: con series cortas un salto inflaría su propio umbral,
        # por eso la serie tiene una longitud realista (los datos reales tienen miles de lecturas)
        t, v = serie(600)
        v.iloc[300:] += 5_000_000.0  # 5000 veces el consumo horario
        out = procesar(t, v)
        self.assertIn("salto", set(out["calidad"]))
        self.assertTrue(out.loc[out["calidad"] == "salto", "wh"].isna().all())
        self.assertLess(out["wh"].max(), 2 * WH_POR_HORA)

    def test_el_umbral_de_salto_es_un_parametro(self):
        t, v = serie(600)
        v.iloc[300:] += 100_000.0  # 100 veces el consumo horario
        estricto = procesar(t, v, thr_x=20)
        laxo = procesar(t, v, thr_x=500)
        self.assertIn("salto", set(estricto["calidad"]))
        self.assertNotIn("salto", set(laxo["calidad"]))

    def test_limitacion_documentada_series_cortas_no_detectan_saltos(self):
        # Limitación conocida (documentacion/04): con pocas lecturas el salto eleva su propio percentil 99 y no se marca.
        t, v = serie(60)
        v.iloc[30:] += 5_000_000.0
        self.assertNotIn("salto", set(procesar(t, v)["calidad"]))

    def test_hueco_de_2_horas_se_interpola_y_el_umbral_es_un_parametro(self):
        t, v = serie(30)
        t, v = t.drop(index=14).reset_index(drop=True), v.drop(index=14).reset_index(drop=True)
        con_umbral_normal = procesar(t, v, hueco_h=CAL["umbral_hueco_interpolable_horas"])
        con_umbral_alto = procesar(t, v, hueco_h=3.0)
        self.assertIn("interpolado", set(con_umbral_normal["calidad"]))
        self.assertNotIn("interpolado", set(con_umbral_alto["calidad"]))
        np.testing.assert_allclose(con_umbral_normal["wh"].dropna(), WH_POR_HORA)  # el reparto lineal conserva el consumo

    def test_hueco_largo_queda_como_faltante(self):
        t, v = serie(60)
        t, v = t.drop(index=range(20, 30)).reset_index(drop=True), v.drop(index=range(20, 30)).reset_index(drop=True)
        out = procesar(t, v, max_h=6)
        self.assertIn("faltante", set(out["calidad"]))
        self.assertTrue(out.loc[out["calidad"] == "faltante", "wh"].isna().all())

    def test_congelamiento_reparte_la_energia_acumulada_y_la_conserva(self):
        # 20 horas normales, 6 horas con el contador quieto y un salto con las 7 horas de consumo acumuladas
        inc = [WH_POR_HORA] * 19 + [0.0] * 5 + [7 * WH_POR_HORA] + [WH_POR_HORA] * 10
        t, v = serie(len(inc) + 1, inc)
        df = pd.DataFrame({"t": t, "A": v, "B": v * 2})
        hora, resumen, cong, _, _ = procesar_planta(df, "RC", ["A", "B"], CAL, K)
        self.assertEqual(len(cong), 1)
        a = hora[hora["medidor"] == "A"]
        est = a[a["calidad"] == "estimado"]
        self.assertGreaterEqual(len(est), 5)
        self.assertTrue(np.allclose(est["kwh"], est["kwh"].iloc[0]))  # reparto uniforme
        total_contador = (v.iloc[-1] - v.iloc[0]) * K
        self.assertAlmostEqual(a["kwh"].sum(), total_contador, places=6)  # la energía total se conserva

    def test_umbral_de_congelamiento_es_un_parametro(self):
        inc = [WH_POR_HORA] * 10 + [0.0, 0.0] + [3 * WH_POR_HORA] + [WH_POR_HORA] * 10
        t, v = serie(len(inc) + 1, inc)
        df = pd.DataFrame({"t": t, "A": v, "B": v * 2})
        con_3 = procesar_planta(df, "RC", ["A", "B"], {**CAL, "min_intervalos_congelado": 3}, K)[2]
        con_2 = procesar_planta(df, "RC", ["A", "B"], {**CAL, "min_intervalos_congelado": 2}, K)[2]
        self.assertEqual(len(con_3), 0)  # 2 horas quietas no alcanzan el umbral de 3
        self.assertEqual(len(con_2), 1)

    def test_una_parada_de_un_solo_medidor_no_es_congelamiento_global(self):
        inc_a = [WH_POR_HORA] * 10 + [0.0] * 6 + [WH_POR_HORA] * 10
        t, a = serie(len(inc_a) + 1, inc_a)
        _, b = serie(len(inc_a) + 1)
        df = pd.DataFrame({"t": t, "A": a, "B": b})
        _, _, cong, _, _ = procesar_planta(df, "RC", ["A", "B"], CAL, K)
        self.assertEqual(len(cong), 0)


N_LECTURAS = 800
RACHAS = cargar_config()["rachas"]


def planta_sintetica(n=N_LECTURAS, ajustes=None, wh_por_hora=None):
    """Tres medidores con consumo de unos 10 kWh/h (con ruido fijo). `ajustes[m]` = (desde, hasta, reaparece): el contador de `m`
    no cambia en los intervalos desde..hasta-1 y, si `reaparece`, la energía de esos intervalos se suma en el intervalo `hasta`."""
    wh_por_hora = wh_por_hora or {}
    cols = {}
    for k, m in enumerate("ABC"):
        rng = np.random.default_rng(k)
        inc = np.clip(wh_por_hora.get(m, 10000.0) * (1 + 0.2 * rng.standard_normal(n - 1)), 0.0, None)
        if m in (ajustes or {}):
            desde, hasta, reaparece = ajustes[m]
            acumulado = inc[desde:hasta + 1].sum()
            inc[desde:hasta] = 0.0
            inc[hasta] = acumulado if reaparece else inc[hasta]
        cols[m] = 100000.0 + np.concatenate([[0.0], np.cumsum(inc)])
    return pd.DataFrame({"t": pd.date_range(INICIO, periods=n, freq="h"), **cols})


def rachas_de(df, medidor=None, **cambios):
    hora, _, cong, _, rachas = procesar_planta(df, "RC", ["A", "B", "C"], CAL, K, {**RACHAS, **cambios})
    return hora, cong, (rachas if medidor is None else rachas[rachas["medidor"] == medidor].reset_index(drop=True))


class PruebasRachas(unittest.TestCase):
    def test_congelamiento_de_un_medidor_con_reaparicion_se_clasifica_y_se_corrige(self):
        df = planta_sintetica(ajustes={"A": (300, 310, True)})
        hora, cong, ra = rachas_de(df, "A")
        self.assertEqual(len(cong), 0)  # los otros medidores seguían: no es un congelamiento de planta
        self.assertEqual(len(ra), 1)
        r = ra.iloc[0]
        self.assertEqual((r["clasificacion"], r["confianza"], r["tratamiento"]), ("congelamiento_scada_medidor", "alta", "estimado_medidor"))
        self.assertEqual(r["n_intervalos"], 10)
        a = hora[hora["medidor"] == "A"]
        self.assertGreaterEqual((a["calidad"] == "estimado").sum(), 10)
        self.assertEqual((hora[hora["medidor"] != "A"]["calidad"] == "estimado").sum(), 0)
        self.assertAlmostEqual(a["kwh"].sum(), (df["A"].iloc[-1] - df["A"].iloc[0]) * K, places=6)  # la energía total se conserva

    def test_sin_la_correccion_solo_se_clasifica(self):
        df = planta_sintetica(ajustes={"A": (300, 310, True)})
        hora, _, ra = rachas_de(df, "A", corregir_congelamiento_por_medidor=0)
        self.assertEqual(ra.iloc[0]["clasificacion"], "congelamiento_scada_medidor")
        self.assertEqual(ra.iloc[0]["tratamiento"], "medido")
        self.assertEqual((hora["calidad"] == "estimado").sum(), 0)

    def test_parada_de_toda_la_planta_sin_reaparicion_es_consumo_cero(self):
        df = planta_sintetica(ajustes={m: (300, 310, False) for m in "ABC"})
        _, cong, ra = rachas_de(df)
        self.assertEqual(len(cong), 1)
        self.assertEqual(set(ra["clasificacion"]), {"sin_consumo_planta"})
        self.assertEqual(set(ra["confianza"]), {"alta"})

    def test_medidor_aislado_sin_reaparicion_con_planta_activa_es_indeterminado(self):
        df = planta_sintetica(ajustes={"A": (300, 310, False)})
        hora, _, ra = rachas_de(df, "A")
        r = ra.iloc[0]
        self.assertEqual((r["clasificacion"], r["confianza"], r["tratamiento"]), ("sin_variacion_planta_activa", "baja", "medido"))
        self.assertEqual((hora["calidad"] == "estimado").sum(), 0)  # no se inventa energía

    def test_medidor_de_bajo_consumo_sin_cambio_es_normal(self):
        df = planta_sintetica(ajustes={"A": (300, 308, False)}, wh_por_hora={"A": 300.0})
        _, _, ra = rachas_de(df, "A")
        self.assertEqual(ra.iloc[0]["clasificacion"], "constante_bajo_consumo")

    def test_umbral_de_bajo_consumo_y_duracion_maxima_son_parametros(self):
        df = planta_sintetica(ajustes={"A": (300, 308, False)}, wh_por_hora={"A": 300.0})
        self.assertNotEqual(rachas_de(df, "A", umbral_bajo_consumo_kwh_h=0.1)[2].iloc[0]["clasificacion"], "constante_bajo_consumo")
        self.assertNotEqual(rachas_de(df, "A", max_horas_bajo_consumo=2)[2].iloc[0]["clasificacion"], "constante_bajo_consumo")

    def test_el_factor_de_reaparicion_es_un_parametro(self):
        df = planta_sintetica(ajustes={"A": (300, 310, True)})
        self.assertNotIn("congelamiento", rachas_de(df, "A", factor_recuperacion_p99=100)[2].iloc[0]["clasificacion"])

    def test_limitacion_documentada_reaparicion_pequena_no_se_detecta(self):
        # un congelamiento corto cuya energía acumulada no supera el umbral de reaparición no se distingue de una reanudación:
        # 4 horas acumuladas (unos 40 kWh) con un umbral de 5 veces el percentil 99 horario (unos 70 kWh)
        df = planta_sintetica(ajustes={"A": (300, 303, True)})
        self.assertIn("congelamiento", rachas_de(df, "A")[2].iloc[0]["clasificacion"])
        r = rachas_de(df, "A", factor_recuperacion_p99=5)[2].iloc[0]
        self.assertNotIn("congelamiento", r["clasificacion"])
        self.assertEqual(r["tratamiento"], "medido")

    def test_racha_al_final_del_archivo_no_tiene_dato_posterior(self):
        df = planta_sintetica(ajustes={"A": (300, 310, True)}).iloc[:306].reset_index(drop=True)
        ra = rachas_de(df, "A")[2]
        self.assertEqual(ra.iloc[0]["clasificacion"], "sin_dato_posterior")
        self.assertEqual(ra.iloc[0]["confianza"], "baja")

    def test_sin_parametros_de_rachas_la_tabla_sale_vacia_y_nada_se_corrige(self):
        df = planta_sintetica(ajustes={"A": (300, 310, True)})
        hora, _, _, _, ra = procesar_planta(df, "RC", ["A", "B", "C"], CAL, K)
        self.assertEqual(len(ra), 0)
        self.assertEqual((hora["calidad"] == "estimado").sum(), 0)

    def test_cobertura_temporal_y_de_energia_no_son_lo_mismo(self):
        from src.datos.energia_comun import tabla_cobertura_mensual
        df = planta_sintetica(ajustes={"A": (300, 330, True)})
        hora, _, _ = rachas_de(df)
        cv = tabla_cobertura_mensual(hora)
        self.assertTrue(((cv["horas_medidas"] + cv["horas_estimadas"] + cv["horas_sin_energia"]) == cv["horas_con_dato"]).all())
        a = cv[(cv["medidor"] == "A")]
        self.assertGreater(a["horas_estimadas"].sum(), 25)
        self.assertEqual(cv[cv["medidor"] == "B"]["horas_estimadas"].sum(), 0)
        enero_a = a[a["mes"] == "2026-01"].iloc[0]
        self.assertAlmostEqual(enero_a["cobertura_temporal"], enero_a["horas_medidas"] / 744, places=3)
        self.assertLess(enero_a["fraccion_energia_medida"], 1.0)
        enero_b = cv[(cv["medidor"] == "B") & (cv["mes"] == "2026-01")].iloc[0]
        self.assertEqual(enero_b["fraccion_energia_medida"], 1.0)


class PruebasConfiguracion(unittest.TestCase):
    def test_cargar_config_devuelve_solo_valores(self):
        cfg = cargar_config()
        self.assertIsInstance(cfg["calidad"]["cobertura_minima"], float)
        self.assertEqual(set(cfg["turnos"]), {1, 2, 3})
        self.assertEqual(horas_por_turno(cfg), {1: 8, 2: 8, 3: 8})

    def test_todo_parametro_tiene_metadatos_y_los_supuestos_advierten(self):
        cat = catalogo()
        self.assertGreater(len(cat), 30)
        for p in cat:
            self.assertTrue(p["descripcion"] and p["justificacion"] and p["unidad"], p["nombre"])
        for p in supuestos_en_uso():
            self.assertTrue(p["advertencia"].strip(), p["nombre"])


if __name__ == "__main__":
    unittest.main()
