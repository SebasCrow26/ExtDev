"""Utilidades compartidas: leer config.yaml y cargar tablas (reales si existen, si no de ejemplo)."""
import os
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
RUTA_CONFIG = RAIZ / "config" / "config.yaml"
COLUMNAS_FECHA = ["fecha_turno", "fecha", "hora_inicio", "vigente_desde"]
CAMPOS_META = ("unidad", "tipo", "descripcion", "justificacion", "advertencia")


def _desenvolver(nodo):
    """Cada parámetro es un bloque con la clave `valor`; devuelve solo los valores, con la misma forma de siempre."""
    if isinstance(nodo, dict):
        if "valor" in nodo:
            return nodo["valor"]
        return {k: _desenvolver(v) for k, v in nodo.items()}
    return nodo


def _leer(ruta=None):
    with open(ruta or RUTA_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_config(ruta=None):
    """Valores de config/config.yaml (sin metadatos). `cfg["calidad"]["cobertura_minima"]`, etc."""
    return _desenvolver(_leer(ruta))


def catalogo(ruta=None):
    """Lista de parámetros con sus metadatos: nombre (con puntos), valor, unidad, tipo, descripcion, justificacion, advertencia."""
    filas = []

    def recorrer(nodo, prefijo):
        for clave, hijo in nodo.items():
            nombre = f"{prefijo}.{clave}" if prefijo else str(clave)
            if isinstance(hijo, dict) and "valor" in hijo:
                filas.append({"nombre": nombre, "valor": hijo["valor"], **{c: hijo.get(c, "") for c in CAMPOS_META}})
            elif isinstance(hijo, dict):
                recorrer(hijo, nombre)

    recorrer(_leer(ruta), "")
    return filas


def supuestos_en_uso(ruta=None):
    """Parámetros de tipo `supuesto` con su advertencia: lo que el equipo debe tener presente al leer resultados."""
    return [p for p in catalogo(ruta) if p["tipo"] == "supuesto"]


def leer_tabla(nombre, usar_ejemplo=None):
    """Lee la tabla `nombre` (sin .csv).

    Usa data/clean si el archivo existe; si no, data/ejemplo.
    Fuerza los datos de ejemplo con usar_ejemplo=True o con la variable de entorno CLARIOS_USAR_EJEMPLO=1.
    La fuente usada queda en df.attrs["fuente"].
    """
    cfg = cargar_config()
    real = RAIZ / cfg["rutas"]["datos_reales"] / f"{nombre}.csv"
    ejemplo = RAIZ / cfg["rutas"]["datos_ejemplo"] / f"{nombre}.csv"
    if usar_ejemplo is None:
        usar_ejemplo = os.environ.get("CLARIOS_USAR_EJEMPLO") == "1" or not real.exists()
    ruta = ejemplo if usar_ejemplo else real
    df = pd.read_csv(ruta)
    for col in COLUMNAS_FECHA:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    df.attrs["fuente"] = "ejemplo" if usar_ejemplo else "real"
    return df


def mapa_procesos(cfg=None):
    """Filas del mapa de procesos de config.yaml (lista de diccionarios con listas de medidores y de líneas)."""
    return (cfg or cargar_config())["mapa_procesos"]


def medidores_proceso(planta, cfg=None):
    """Medidores del SCADA de los procesos que se modelan (`modelar: true`) de una planta."""
    return [m for p in mapa_procesos(cfg) if p["planta"] == planta and p["modelar"] for m in p["medidores_scada"]]


def lineas_a_proceso(cfg=None):
    """Diccionario línea del ERP -> proceso de modelado, según el mapa de config.yaml."""
    return {linea: p["proceso_modelo"] for p in mapa_procesos(cfg) for linea in p["lineas_erp"]}


def tabla_mapa_procesos(cfg=None):
    """DataFrame del mapa de procesos con el formato de data/clean/mapa_procesos.csv (listas unidas con punto y coma)."""
    filas = [[p["planta"], p["proceso_modelo"], ";".join(p["medidores_scada"]), ";".join(p["lineas_erp"]), p["unidad_produccion"], p["nota"]]
             for p in mapa_procesos(cfg)]
    return pd.DataFrame(filas, columns=["planta", "proceso_modelo", "medidores_scada", "lineas_erp", "unidad_produccion", "nota"])
