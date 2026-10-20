"""Pruebas del validador del contrato (tools/validar_contrato.py).

Cada prueba copia el repositorio mínimo (config, documentos y data/clean) a una carpeta temporal, introduce UN defecto
y comprueba que el validador lo detecta con la severidad y el código de salida esperados.

Uso (desde la raíz del repositorio):  python -m unittest discover -s tests -v
No requiere pytest ni dependencias adicionales.
"""
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import validar_contrato  # noqa: E402


def copiar_arbol(destino):
    destino = Path(destino)
    for rel in ("config", "documentacion/01_contrato_datos.md", "documentacion/04_supuestos_y_limitaciones.md", "documentacion/12_diccionario_datos.md", "documentacion/13_parametros.md"):
        origen = RAIZ / rel
        if origen.is_dir():
            shutil.copytree(origen, destino / rel)
        else:
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(origen, destino / rel)
    shutil.copytree(RAIZ / "datos_simulados", destino / "data" / "clean", ignore=shutil.ignore_patterns("*.md", ".gitkeep"))


def mutar(raiz, tabla, fn):
    ruta = Path(raiz) / "data" / "clean" / f"{tabla}.csv"
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    df = fn(df)
    df.to_csv(ruta, index=False, lineterminator="\n")


def ejecutar(raiz, *extra):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        codigo = validar_contrato.main(["--raiz", str(raiz), "--sin-raw", *extra])
    return codigo, salida.getvalue()


def informe(raiz):
    ruta = Path(raiz) / "informe.json"
    ejecutar(raiz, "--json", str(ruta))
    return json.loads(ruta.read_text(encoding="utf-8"))


def huella(carpeta):
    h = hashlib.sha256()
    for p in sorted(Path(carpeta).rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()


class PruebasValidador(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        copiar_arbol(self.raiz)

    def tearDown(self):
        self._tmp.cleanup()

    def incidencias(self, severidad=None, tabla=None, texto=None):
        inc = informe(self.raiz)["incidencias"]
        return [i for i in inc if (severidad is None or i["severidad"] == severidad) and (tabla is None or i["tabla"] == tabla)
                and (texto is None or texto in i["prueba"] or texto in i["detalle"])]

    # ---------- caso válido ----------
    def test_01_datos_reales_son_aptos_sin_bloqueantes(self):
        codigo, salida = ejecutar(self.raiz)
        self.assertEqual(codigo, 0, salida[-1500:])
        self.assertIn("APTO", salida)
        self.assertEqual(self.incidencias("critico"), [])
        self.assertEqual(self.incidencias("alto"), [])

    def test_02_declara_lo_no_verificable(self):
        _, salida = ejecutar(self.raiz)
        self.assertIn("NO VERIFICABLE", salida)
        self.assertIn("Calendario real de turnos", salida)
        self.assertIn("Plan de producción y presupuesto FY27", salida)

    def test_03_no_modifica_los_datos(self):
        antes = huella(self.raiz / "data" / "clean")
        ejecutar(self.raiz)
        self.assertEqual(antes, huella(self.raiz / "data" / "clean"))

    def test_04_es_determinista(self):
        a, b = informe(self.raiz), informe(self.raiz)
        self.assertEqual(a, b)

    # ---------- casos inválidos ----------
    def test_10_columna_obligatoria_faltante_es_critica(self):
        mutar(self.raiz, "energia_turno", lambda d: d.drop(columns=["turno"]))
        codigo, _ = ejecutar(self.raiz)
        self.assertEqual(codigo, 1)
        self.assertTrue(self.incidencias("critico", "energia_turno", "columnas obligatorias"))

    def test_11_clave_duplicada_es_critica(self):
        mutar(self.raiz, "produccion_turno", lambda d: pd.concat([d, d.iloc[[5]]], ignore_index=True))
        self.assertTrue(self.incidencias("critico", "produccion_turno", "clave única"))

    def test_12_kwh_negativo_es_alto(self):
        def f(d):
            d.loc[10, "kwh"] = "-5"
            d.loc[10, "calidad"] = "ok"
            return d
        mutar(self.raiz, "energia_hora", f)
        self.assertTrue(self.incidencias("alto", "energia_hora", "`kwh` dentro del rango"))

    def test_13_hueco_temporal_se_detecta(self):
        def f(d):
            idx = d.index[(d.medidor == "HORNO")][500]
            return d.drop(index=idx)
        mutar(self.raiz, "energia_hora", f)
        self.assertTrue(self.incidencias("alto", "energia_hora", "continuidad"))

    def test_14_agregacion_que_no_suma_es_critica(self):
        def f(d):
            d.loc[100, "kwh"] = str(float(d.loc[100, "kwh"] or 0) + 10)
            return d
        mutar(self.raiz, "energia_turno", f)
        codigo, _ = ejecutar(self.raiz)
        self.assertEqual(codigo, 1)
        self.assertTrue(self.incidencias("critico", "energia_turno", "suma de horas válidas"))

    def test_15_nulo_en_columna_clave_es_critico(self):
        def f(d):
            d.loc[3, "fecha_turno"] = ""
            return d
        mutar(self.raiz, "dataset_modelo", f)
        self.assertTrue(self.incidencias("critico", "dataset_modelo", "sin nulos"))

    def test_16_valor_fuera_de_rango_y_no_permitido(self):
        def f(d):
            d.loc[3, "turno"] = "4"
            d.loc[7, "unidad"] = "toneladas"
            return d
        mutar(self.raiz, "dataset_modelo", f)
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "`turno` dentro del rango"))
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "valores permitidos"))

    def test_17_unidad_distinta_a_la_del_mapa_es_alta(self):
        def f(d):
            d.loc[d.proceso_modelo == "formacion", "unidad"] = "kg"
            return d
        mutar(self.raiz, "dataset_modelo", f)
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "unidad del mapa"))

    def test_18_tipo_invalido_es_critico(self):
        def f(d):
            d.loc[4, "cobertura"] = "mucha"
            return d
        mutar(self.raiz, "dataset_modelo", f)
        self.assertTrue(self.incidencias("critico", "dataset_modelo", "tipo float"))

    def test_19_calidad_ok_incoherente_con_la_cobertura(self):
        def f(d):
            i = d.index[(d.calidad_ok == "1")][0]
            d.loc[i, "calidad_ok"] = "0"
            return d
        mutar(self.raiz, "dataset_modelo", f)
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "calidad_ok"))

    def test_20_dia_que_no_suma_sus_turnos_es_critico(self):
        def f(d):
            d.loc[50, "produccion"] = str(float(d.loc[50, "produccion"]) + 1000)
            return d
        mutar(self.raiz, "dataset_modelo_dia", f)
        self.assertTrue(self.incidencias("critico", "dataset_modelo_dia", "día = suma de sus turnos"))

    def test_21_columna_no_declarada_es_solo_advertencia(self):
        mutar(self.raiz, "gas_dia", lambda d: d.assign(extra="x"))
        codigo, _ = ejecutar(self.raiz)
        self.assertEqual(codigo, 0)
        self.assertTrue(self.incidencias("medio", "gas_dia", "no declaradas"))
        codigo_estricto, _ = ejecutar(self.raiz, "--estricto")
        self.assertEqual(codigo_estricto, 1)

    def test_22_tabla_faltante_es_critica(self):
        (self.raiz / "data" / "clean" / "gas_dia.csv").unlink()
        codigo, _ = ejecutar(self.raiz)
        self.assertEqual(codigo, 1)
        self.assertTrue(self.incidencias("critico", "gas_dia", "existencia"))

    def test_23_limitacion_critica_sin_documentar_es_alta(self):
        ruta = self.raiz / "documentacion" / "04_supuestos_y_limitaciones.md"
        ruta.write_text(ruta.read_text(encoding="utf-8").replace("EMCALI", "XXXXX"), encoding="utf-8")
        self.assertTrue(self.incidencias("alto", "documentacion/04_supuestos_y_limitaciones.md", "EMCALI"))

    def test_24_parametro_de_configuracion_faltante_es_alto(self):
        ruta = self.raiz / "config" / "config.yaml"
        texto = ruta.read_text(encoding="utf-8").replace("tarifa_kwh_cop", "tarifa_otra")
        ruta.write_text(texto, encoding="utf-8")
        self.assertTrue(self.incidencias("alto", "config.yaml", "tarifas.tarifa_kwh_cop"))

    def test_25_diccionario_desactualizado_es_advertencia(self):
        ruta = self.raiz / "documentacion" / "12_diccionario_datos.md"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\nlínea añadida a mano\n", encoding="utf-8")
        self.assertTrue(self.incidencias("medio", None, "diccionario"))

    def test_26_sin_contrato_es_error_de_uso(self):
        (self.raiz / "config" / "contrato_datos.yaml").unlink()
        codigo, _ = ejecutar(self.raiz)
        self.assertEqual(codigo, 2)

    def test_27_tabla_sin_contrato_se_advierte(self):
        shutil.copy(self.raiz / "data" / "clean" / "gas_dia.csv", self.raiz / "data" / "clean" / "tabla_nueva.csv")
        self.assertTrue(self.incidencias("medio", "data/clean", "tiene contrato"))


    # ---------- parámetros ----------
    def _editar_config(self, fn):
        ruta = self.raiz / "config" / "config.yaml"
        cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        fn(cfg)
        ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def test_30_supuesto_sin_advertencia_es_alto(self):
        self._editar_config(lambda c: c["turnos"].__setitem__("advertencia", ""))
        self.assertTrue(self.incidencias("alto", "config.yaml", "todo supuesto declara su advertencia"))

    def test_31_parametro_sin_justificacion_es_advertencia(self):
        self._editar_config(lambda c: c["calidad"]["cobertura_minima"].__setitem__("justificacion", ""))
        self.assertTrue(self.incidencias("medio", "config.yaml", "descripción y justificación"))

    def test_32_tipo_de_parametro_invalido_es_alto(self):
        self._editar_config(lambda c: c["calidad"]["cobertura_minima"].__setitem__("tipo", "capricho"))
        self.assertTrue(self.incidencias("alto", "config.yaml", "tipo válido"))

    def test_33_documento_de_parametros_desactualizado_es_advertencia(self):
        ruta = self.raiz / "documentacion" / "13_parametros.md"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\nlínea añadida a mano\n", encoding="utf-8")
        self.assertTrue(self.incidencias("medio", "documentacion/13_parametros.md", "al día"))

    def test_34_turnos_que_no_duran_8_horas_son_altos(self):
        def f(c):
            c["turnos"]["valor"] = {1: {"inicio": "06:00", "fin": "18:00"}, 2: {"inicio": "18:00", "fin": "06:00"}}
        self._editar_config(f)
        self.assertTrue(self.incidencias("alto", "config.yaml", "8 horas"))

    def test_35_lista_los_supuestos_en_uso(self):
        _, salida = ejecutar(self.raiz)
        self.assertIn("SUPUESTOS EN USO", salida)
        self.assertIn("turnos", salida)
        sup = informe(self.raiz)["supuestos_en_uso"]
        self.assertGreaterEqual(len(sup), 5)
        self.assertTrue(all(x["advertencia"] for x in sup))

    def test_36_falta_un_parametro_requerido(self):
        self._editar_config(lambda c: c["gas"].pop("hueco_estimado_horas"))
        self.assertTrue(self.incidencias("alto", "config.yaml", "gas.hueco_estimado_horas"))

    # ---------- rachas por medidor y cobertura ----------
    def test_40_racha_corregida_sin_horas_estimadas_es_alta(self):
        def f(d):
            d.loc[(d.planta == "F&A") & (d.medidor == "RECTIFICADOR_2") & (d.calidad == "estimado"), "calidad"] = "ok"
            return d
        mutar(self.raiz, "energia_hora", f)
        self.assertTrue(self.incidencias("alto", "rachas_constantes_energia", "horas marcadas `estimado`"))

    def test_41_congelamiento_sin_tratar_es_alto(self):
        def f(d):
            d.loc[d.clasificacion == "congelamiento_scada_medidor", "tratamiento"] = "medido"
            return d
        mutar(self.raiz, "rachas_constantes_energia", f)
        self.assertTrue(self.incidencias("alto", "rachas_constantes_energia", "ningún congelamiento"))

    def test_42_clasificacion_fuera_de_catalogo_es_advertencia_de_valores(self):
        def f(d):
            d.loc[0, "clasificacion"] = "inventada"
            return d
        mutar(self.raiz, "rachas_constantes_energia", f)
        self.assertTrue(self.incidencias(None, "rachas_constantes_energia", "valores permitidos"))

    def test_43_cobertura_mensual_que_no_cuadra_con_energia_hora_es_critica(self):
        def f(d):
            d.loc[3, "kwh_medido"] = str(float(d.loc[3, "kwh_medido"]) + 500)
            return d
        mutar(self.raiz, "cobertura_energia_mensual", f)
        self.assertTrue(self.incidencias("critico", "cobertura_energia_mensual", "kWh medido"))

    def test_45_resultado_del_modelo_con_energia_distinta_a_dataset_modelo_es_alto(self):
        def f(d):
            d.loc[7, "kwh_real"] = str(float(d.loc[7, "kwh_real"]) + 50)
            return d
        mutar(self.raiz, "resultados_modelo", f)
        self.assertTrue(self.incidencias("alto", "resultados_modelo", "kwh_real del modelo"))

    def test_46_pronostico_con_intervalo_incoherente_se_advierte(self):
        def f(d):
            d.loc[0, "kwh_inferior"] = str(float(d.loc[0, "kwh_superior"]) + 100)
            return d
        mutar(self.raiz, "pronostico", f)
        self.assertTrue(self.incidencias("medio", "pronostico", "kwh_inferior"))

    def _escalar_horno(self, columnas, factor):
        """Multiplica columnas del horno en las tres tablas de modelado a la vez, para que las sumas internas sigan cuadrando."""
        def f(d):
            mk = d["proceso_modelo"] == "horno"
            for c in columnas:
                x = pd.to_numeric(d.loc[mk, c], errors="coerce") * factor
                d.loc[mk, c] = x.round(3).astype(str).replace("nan", "")
            return d
        for t in ("dataset_modelo", "dataset_modelo_dia", "dataset_modelo_semana"):
            mutar(self.raiz, t, f)

    def test_47_energia_de_dataset_modelo_que_no_viene_de_energia_turno_es_alta(self):
        self._escalar_horno(["kwh", "kwh_observado"], 10)
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "kwh_observado de dataset_modelo"))

    def test_48_produccion_de_dataset_modelo_que_no_viene_de_produccion_turno_es_alta(self):
        self._escalar_horno(["produccion"], 2)
        self.assertTrue(self.incidencias("alto", "dataset_modelo", "produccion de dataset_modelo"))

    def test_44_cobertura_temporal_inconsistente_se_advierte(self):
        def f(d):
            d.loc[3, "cobertura_temporal"] = "0.5" if float(d.loc[3, "cobertura_temporal"]) != 0.5 else "0.4"
            return d
        mutar(self.raiz, "cobertura_energia_mensual", f)
        self.assertTrue(self.incidencias("medio", "cobertura_energia_mensual", "cobertura temporal"))


if __name__ == "__main__":
    unittest.main()
