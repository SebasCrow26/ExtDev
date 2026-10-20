"""Utilidades compartidas del frente de Modelos (Joshua).

Todo lo que comparten 01..05 y evaluar.py vive aquí: lectura de tablas, features,
métricas (MAE, WAPE, R²) y el split temporal por fechas de `config/config.yaml`.

Reglas de modelado heredadas de documentacion/03_especificacion_modelos.md y documentacion/09_eda_rc.md:
- No usar `operando` ni `regimen_operacion_rc` como variables explicativas (fuga de información).
- No sumar producción entre procesos (en filtros y ptari es la de refinación, supuesto).
- La producción de RC se reporta por lotes: modelar por día y semana; por turno, anomalías sin producción.
- Entrenar con datos recientes; el triturado cambió de nivel (deriva desde 2023).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.comun.config import cargar_config, leer_tabla

# Procesos cuya energía se explica (los demás del mapa están en modelar: false).
PROCESOS_RC = ["triturado", "horno", "refinacion", "filtros", "ptari"]
PROCESO_FA = "formacion"
SEMILLA = 0  # reproducibilidad; coincide con eda.semilla del config.yaml


def cfg_modelos():
    """config/config.yaml solo con la sección `modelos` + tarifa."""
    c = cargar_config()
    return {
        "inicio_entrenamiento": c["modelos"]["inicio_entrenamiento"],
        "fin_entrenamiento": c["modelos"]["fin_entrenamiento"],
        "inicio_prueba": c["modelos"]["inicio_prueba"],
        "fin_prueba": c["modelos"]["fin_prueba"],
        "fraccion_evitable": c["modelos"]["fraccion_evitable"],
        "percentil_meta": c["modelos"]["percentil_meta"],
        "tarifa_kwh_cop": c["tarifas"]["tarifa_kwh_cop"],
        "gas_cop_m3": c["tarifas"]["gas_cop_m3"],
        "cobertura_minima": c["calidad"]["cobertura_minima"],
    }


def tarifa_mensual():
    """Serie (mes -> COP/kWh) de Clarios con los meses faltantes rellenados hacia adelante."""
    t = leer_tabla("tarifa_kwh_mensual").sort_values("mes")
    t["mes"] = t["mes"].dt.to_period("M").dt.to_timestamp()
    return t.set_index("mes")["costo_kwh_cop"]


def tarifa_para(fechas):
    """Tarifa promedio de Clarios para un rango de fechas (fallback: config.yaml)."""
    cfg = cfg_modelos()
    serie = tarifa_mensual()
    if serie.empty:
        return cfg["tarifa_kwh_cop"]
    fechas = pd.to_datetime(fechas)
    return float(serie.reindex(pd.date_range(serie.index.min(), fechas.max(), freq="MS")).ffill().loc[: fechas.max()].mean())


def agregar_dia(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `dataset_modelo` (turno) a día, solo días con los 3 turnos por proceso."""
    g = (df.groupby(["fecha_turno", "planta", "proceso_modelo"], as_index=False)
           .agg(kwh=("kwh", "sum"), kwh_observado=("kwh_observado", "sum"), produccion=("produccion", "sum"),
                n_transacciones=("n_transacciones", "sum"), cobertura=("cobertura", "mean"),
                calidad_ok=("calidad_ok", "min"), n_turnos=("turno", "nunique")))
    g = g[g["n_turnos"] == 3].drop(columns="n_turnos")
    g["dia_semana"] = g["fecha_turno"].dt.dayofweek
    g["es_fin_semana"] = (g["dia_semana"] >= 5).astype(int)
    return g


def agregar_semana(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega `dataset_modelo` (turno) a semana (lun-dom), solo semanas completas (21 turnos)."""
    d = df.copy()
    d["semana_inicio"] = d["fecha_turno"] - pd.to_timedelta(d["dia_semana"], unit="D")
    g = (d.groupby(["semana_inicio", "planta", "proceso_modelo"], as_index=False)
           .agg(kwh=("kwh", "sum"), kwh_observado=("kwh_observado", "sum"), produccion=("produccion", "sum"),
                n_transacciones=("n_transacciones", "sum"), cobertura=("cobertura", "mean"),
                calidad_ok=("calidad_ok", "min"), n_turnos=("turno", "size")))
    return g[g["n_turnos"] == 21].drop(columns="n_turnos")


def split_temporal(df: pd.DataFrame, col_fecha: str):
    """Divide en entrenamiento y prueba por fechas de config.yaml (nunca aleatorio)."""
    c = cfg_modelos()
    f = df[col_fecha]
    ent = df[(f >= c["inicio_entrenamiento"]) & (f <= c["fin_entrenamiento"])]
    pry = df[(f >= c["inicio_prueba"]) & (f <= c["fin_prueba"])]
    return ent.copy(), pry.copy()


def metricas(y_real, y_pred) -> dict:
    """MAE, WAPE y R²; WAPE en % (evita la división por cero del R² cuando todo es constante)."""
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    m = ~np.isnan(y_real) & ~np.isnan(y_pred)
    y_real, y_pred = y_real[m], y_pred[m]
    if len(y_real) == 0:
        return {"mae": np.nan, "wape": np.nan, "r2": np.nan, "n": 0}
    mae = float(np.mean(np.abs(y_real - y_pred)))
    wape = 100 * mae / float(np.sum(np.abs(y_real))) if np.sum(np.abs(y_real)) > 0 else np.nan
    # R² clásico (1 - SS_res/SS_tot) frente a la media REAL; un predictor plano da R² = 0 y uno malo, negativo.
    ss_res = float(np.sum((y_real - y_pred) ** 2))
    ss_tot = float(np.sum((y_real - np.mean(y_real)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"mae": round(mae, 2), "wape": round(wape, 2), "r2": round(r2, 4), "n": int(len(y_real))}


def mad(x) -> float:
    """Desviación absoluta mediana (robusta)."""
    x = np.asarray(x, dtype=float)
    return float(np.median(np.abs(x - np.median(x))))


def z_robusto(residuos) -> np.ndarray:
    """Residuos estandarizados con mediana y MAD (máx(1, 1.4826*MAD) como escala)."""
    r = np.asarray(residuos, dtype=float)
    escala = max(mad(r), 1.0) * 1.4826
    return (r - np.median(r)) / escala
