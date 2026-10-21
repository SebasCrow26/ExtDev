"""Utilidades compartidas: leer config.yaml y cargar exclusivamente tablas sintéticas."""
import os
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parent   # carpeta dashboard/
RUTA_CONFIG = RAIZ / "config.yaml"
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


def carpeta_datos_reales():
    """Carpeta local con las tablas reales, solo si se definió la variable de entorno CLARIOS_DATOS_REALES (uso local; nunca en un despliegue público)."""
    ruta = os.environ.get("CLARIOS_DATOS_REALES")
    return Path(ruta) if ruta else None


def leer_tabla(nombre, usar_ejemplo=None):
    """Lee la tabla `nombre`. Por defecto usa las tablas sintéticas de datos_simulados/.

    Si la variable de entorno CLARIOS_DATOS_REALES apunta a una carpeta con las tablas reales, lee de ahí (solo en local).
    El despliegue público no define esa variable, así que ahí siempre se leen las sintéticas.
    """
    real = carpeta_datos_reales()
    if real is not None and usar_ejemplo is not True:
        ruta, fuente = real / f"{nombre}.csv", "real"
    else:
        cfg = cargar_config()
        ruta, fuente = RAIZ / cfg["rutas"]["datos_ejemplo"] / f"{nombre}.csv", "sintético"
    if usar_ejemplo is False and real is None:
        raise ValueError("Sin CLARIOS_DATOS_REALES solo se pueden cargar datos sintéticos.")
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la tabla requerida: {ruta}")
    df = pd.read_csv(ruta)
    for col in COLUMNAS_FECHA:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    df.attrs["fuente"] = fuente
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
    """DataFrame del mapa de procesos con el formato de data/clean (dentro de dashboard/)/mapa_procesos.csv (listas unidas con punto y coma)."""
    filas = [[p["planta"], p["proceso_modelo"], ";".join(p["medidores_scada"]), ";".join(p["lineas_erp"]), p["unidad_produccion"], p["nota"]]
             for p in mapa_procesos(cfg)]
    return pd.DataFrame(filas, columns=["planta", "proceso_modelo", "medidores_scada", "lineas_erp", "unidad_produccion", "nota"])
