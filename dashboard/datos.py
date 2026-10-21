"""datos.py — Capa de acceso a datos, semáforo, alertas y tarifas para el dashboard.

Centraliza todas las lecturas de tablas con @st.cache_data y la lógica de negocio
(semáforo, reglas de alertas, resolución de tarifas y agregaciones).
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

import sys
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dashboard.configuracion import cargar_config, leer_tabla, supuestos_en_uso, catalogo
from dashboard.turnos import orden_turnos_cronologico


# ==============================================================================
# 1. CARGA DE TABLAS CON CACHÉ
# ==============================================================================

@st.cache_data
def get_config():
    """Carga config/config.yaml."""
    return cargar_config()


@st.cache_data
def get_supuestos():
    """Lista de supuestos con metadatos y advertencias."""
    return supuestos_en_uso()


@st.cache_data
def get_catalogo_parametros():
    """Catálogo completo de parámetros."""
    return catalogo()


@st.cache_data
def get_resultados_modelo() -> pd.DataFrame:
    """Tabla resultados_modelo (año fiscal 2026 para RC)."""
    df = leer_tabla("resultados_modelo")
    df["fecha_turno"] = pd.to_datetime(df["fecha_turno"])
    return df


@st.cache_data
def get_dataset_modelo() -> pd.DataFrame:
    """Tabla dataset_modelo (por turno, incluye calidad_ok y producción)."""
    df = leer_tabla("dataset_modelo")
    df["fecha_turno"] = pd.to_datetime(df["fecha_turno"])
    return df


@st.cache_data
def get_dataset_modelo_dia() -> pd.DataFrame:
    """Tabla dataset_modelo_dia."""
    df = leer_tabla("dataset_modelo_dia")
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data
def get_dataset_modelo_semana() -> pd.DataFrame:
    """Tabla dataset_modelo_semana (para intensidades semanales)."""
    df = leer_tabla("dataset_modelo_semana")
    df["semana_inicio"] = pd.to_datetime(df["semana_inicio"])
    return df


@st.cache_data
def get_metas() -> pd.DataFrame:
    """Metas sintéticas de intensidad."""
    return leer_tabla("metas")


@st.cache_data
def get_metas_clarios() -> pd.DataFrame:
    """Metas presupuestarias sintéticas de referencia."""
    return leer_tabla("metas_clarios")


@st.cache_data
def get_tarifa_kwh_mensual() -> pd.DataFrame:
    """Tarifa del kWh por mes (COP/kWh)."""
    df = leer_tabla("tarifa_kwh_mensual")
    df["mes"] = pd.to_datetime(df["mes"])
    return df.sort_values("mes").reset_index(drop=True)


@st.cache_data
def get_anomalias_candidatas_rc() -> pd.DataFrame:
    """25 candidatos a anomalías por mediana/MAD."""
    df = leer_tabla("anomalias_candidatas_rc")
    df["fecha_turno"] = pd.to_datetime(df["fecha_turno"])
    return df


@st.cache_data
def get_pronostico() -> pd.DataFrame:
    """Tabla de pronóstico demostrativo de RC."""
    df = leer_tabla("pronostico")
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data
def get_pronostico_mensual_plantas() -> pd.DataFrame:
    """Pronóstico mensual de Ensamble y OREC."""
    df = leer_tabla("pronostico_mensual_plantas")
    df["mes_pronosticado"] = pd.to_datetime(df["mes_pronosticado"])
    return df


@st.cache_data
def get_base_mensual_plantas() -> pd.DataFrame:
    """Base mensual histórica de plantas (RC, Ensamble, F&A, OREC)."""
    df = leer_tabla("base_mensual_plantas")
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data
def get_gas_dia() -> pd.DataFrame:
    """Consumo diario de gas de refinación (SCADA)."""
    df = leer_tabla("gas_dia")
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data
def get_dataset_gas_dia() -> pd.DataFrame:
    """Dataset modelo gas diario."""
    df = leer_tabla("dataset_modelo_gas_dia")
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data
def get_base_mensual_gas_rc() -> pd.DataFrame:
    """Base mensual de gas de Clarios."""
    df = leer_tabla("base_mensual_gas_rc")
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data
def get_calidad_energia_rc() -> pd.DataFrame:
    return leer_tabla("calidad_energia_rc")


@st.cache_data
def get_calidad_energia_fa() -> pd.DataFrame:
    return leer_tabla("calidad_energia_fa")


@st.cache_data
def get_cobertura_energia_mensual() -> pd.DataFrame:
    df = leer_tabla("cobertura_energia_mensual")
    df["mes"] = pd.to_datetime(df["mes"])
    return df


@st.cache_data
def get_congelamientos_energia_rc() -> pd.DataFrame:
    df = leer_tabla("congelamientos_energia_rc")
    df["inicio"] = pd.to_datetime(df["inicio"])
    df["fin"] = pd.to_datetime(df["fin"])
    return df


@st.cache_data
def get_congelamientos_energia_fa() -> pd.DataFrame:
    df = leer_tabla("congelamientos_energia_fa")
    df["inicio"] = pd.to_datetime(df["inicio"])
    df["fin"] = pd.to_datetime(df["fin"])
    return df


@st.cache_data
def get_rachas_constantes_energia() -> pd.DataFrame:
    df = leer_tabla("rachas_constantes_energia")
    df["inicio"] = pd.to_datetime(df["inicio"])
    df["fin"] = pd.to_datetime(df["fin"])
    return df


@st.cache_data
def get_validacion_energia_rc_mensual() -> pd.DataFrame:
    df = leer_tabla("validacion_energia_rc_mensual")
    df["mes"] = pd.to_datetime(df["mes"])
    return df


# ==============================================================================
# 2. RESOLUCIÓN DE TARIFAS Y COSTOS
# ==============================================================================

def resolver_tarifa(
    fecha_o_mes: pd.Timestamp | str,
    tarifas_df: pd.DataFrame | None = None,
    tarifa_override: float | None = None
) -> tuple[float, bool, str]:
    """Resuelve la tarifa aplicable (COP/kWh).

    Retorna: (tarifa, es_estimada_o_fallback, nota_explicativa)
    Regla: Si hay override en sidebar, lo usa. Si no, busca el mes en tarifa_kwh_mensual.
    Si el mes no existe (ej. ago o sep 2026), usa la última disponible con una nota.
    """
    if tarifa_override is not None and tarifa_override > 0:
        return float(tarifa_override), False, f"Tarifa personalizada por usuario: {tarifa_override:,.2f} COP/kWh"

    if tarifas_df is None:
        tarifas_df = get_tarifa_kwh_mensual()

    fecha = pd.to_datetime(fecha_o_mes)
    mes_str = fecha.strftime("%Y-%m-01")
    mes_ts = pd.to_datetime(mes_str)

    match = tarifas_df[tarifas_df["mes"] == mes_ts]
    if not match.empty:
        tarifa = float(match["costo_kwh_cop"].iloc[0])
        return tarifa, False, f"Tarifa sintética ({fecha.strftime('%b %Y')}): {tarifa:,.2f} COP/kWh"

    # Fallback: última disponible
    ult_fila = tarifas_df.iloc[-1]
    tarifa = float(ult_fila["costo_kwh_cop"])
    ult_mes = ult_fila["mes"].strftime("%b %Y")
    return (
        tarifa,
        True,
        f"Tarifa última disponible ({ult_mes}): {tarifa:,.2f} COP/kWh (mes {fecha.strftime('%b %Y')} sin tarifa en base sintética)"
    )


def calcular_costo_kwh(
    kwh: float,
    fecha: pd.Timestamp | str,
    tarifas_df: pd.DataFrame | None = None,
    tarifa_override: float | None = None
) -> tuple[float, float, bool, str]:
    """Calcula costo en COP a partir de kWh y fecha."""
    tarifa, fallback, nota = resolver_tarifa(fecha, tarifas_df, tarifa_override)
    costo = kwh * tarifa
    return costo, tarifa, fallback, nota


# ==============================================================================
# 3. CÁLCULO DEL SEMÁFORO (REGLA SECCIÓN 4)
# ==============================================================================

def calcular_semaforo_proceso(
    df_res_proc: pd.DataFrame,
    df_dm_proc: pd.DataFrame,
    verde_hasta_pct: float = 5.0,
    amarillo_hasta_pct: float = 10.0
) -> dict:
    """Calcula el semáforo sobre las sumas del periodo para un proceso de RC.

    Regla exacta:
    esperado = d.kwh_esperado.sum()
    pct = 100 * (d.kwh_real.sum() - esperado) / esperado
    turnos_validos = (dataset_modelo[proceso, periodo].calidad_ok).mean()
    if turnos_validos < 0.75: color = "gris"
    elif (d.severidad == "alta").any() or pct > amarillo_hasta_pct: color = "rojo"
    elif pct > verde_hasta_pct: color = "amarillo"
    else: color = "verde"
    indicativo = d.confianza_modelo.iloc[0] == "baja"
    """
    if df_res_proc.empty:
        return {
            "color": "gris",
            "estado": "Sin datos",
            "pct": 0.0,
            "kwh_real": 0.0,
            "kwh_esperado": 0.0,
            "exceso_kwh": 0.0,
            "confianza": "desconocida",
            "indicativo": False,
            "turnos_validos": 0.0,
            "severidad_alta": False,
            "n_turnos": 0
        }

    kwh_real = float(df_res_proc["kwh_real"].sum())
    kwh_esperado = float(df_res_proc["kwh_esperado"].sum())
    exceso_kwh = kwh_real - kwh_esperado
    pct = 100.0 * exceso_kwh / kwh_esperado if kwh_esperado > 0 else 0.0

    if not df_dm_proc.empty and "calidad_ok" in df_dm_proc.columns:
        turnos_validos = float(df_dm_proc["calidad_ok"].mean())
    else:
        turnos_validos = 1.0

    severidad_alta = (df_res_proc["severidad"] == "alta").any() if "severidad" in df_res_proc.columns else False
    confianza = str(df_res_proc["confianza_modelo"].iloc[0]) if "confianza_modelo" in df_res_proc.columns else "media"
    indicativo = (confianza == "baja")

    if turnos_validos < 0.75:
        color = "gris"
        estado = "Dato incompleto (< 75% válidos)"
    elif severidad_alta or pct > amarillo_hasta_pct:
        color = "rojo"
        estado = "Exceso crítico (> 10% o severidad alta)"
    elif pct > verde_hasta_pct:
        color = "amarillo"
        estado = "Desviación moderada (5% a 10%)"
    else:
        color = "verde"
        estado = "En rango objetivo (<= 5%)"

    return {
        "color": color,
        "estado": estado,
        "pct": pct,
        "kwh_real": kwh_real,
        "kwh_esperado": kwh_esperado,
        "exceso_kwh": exceso_kwh,
        "confianza": confianza,
        "indicativo": indicativo,
        "turnos_validos": turnos_validos,
        "severidad_alta": severidad_alta,
        "n_turnos": len(df_res_proc)
    }


# ==============================================================================
# 4. REGLAS DE ALERTAS (SECCIÓN 5)
# ==============================================================================

def calcular_alertas_exceso_sostenido(
    df_res: pd.DataFrame,
    min_turnos: int = 3,
    pct_umbral: float = 10.0,
    min_costo_cop: float = 100000.0,
    filtro_confianza: str = "firmes"  # "firmes" (alta/media), "indicativas" (baja), "todas"
) -> pd.DataFrame:
    """Alerta 1: Rachas de turnos consecutivos con exceso_kwh > pct_umbral % * kwh_esperado.

    Alerta si:
    - len(racha) >= min_turnos
    - sum(costo_exceso_cop) >= min_costo_cop
    - filtro_confianza: 'firmes' (omite baja), 'indicativas' (solo baja), 'todas' (sin filtro).
    """
    filas = []
    orden_turno = orden_turnos_cronologico()
    df_ord = df_res.copy()
    df_ord["_orden_turno"] = df_ord["turno"].map(orden_turno)
    df_ord = df_ord.sort_values(["proceso_modelo", "fecha_turno", "_orden_turno"])

    for proc, g in df_ord.groupby("proceso_modelo"):
        conf = str(g["confianza_modelo"].iloc[0]) if "confianza_modelo" in g else "media"
        es_baja = (conf == "baja")

        if filtro_confianza == "firmes" and es_baja:
            continue
        if filtro_confianza == "indicativas" and not es_baja:
            continue

        g = g.sort_values(["fecha_turno", "_orden_turno"]).reset_index(drop=True)
        cond = (g["kwh_esperado"] > 0) & (g["exceso_kwh"] > (pct_umbral / 100.0) * g["kwh_esperado"])

        racha_id = (~cond).cumsum()
        for _, grupo in g[cond].groupby(racha_id):
            if len(grupo) >= min_turnos:
                costo_tot = float(grupo["costo_exceso_cop"].sum())
                if costo_tot >= min_costo_cop:
                    exceso_tot = float(grupo["exceso_kwh"].sum())
                    kwh_real_tot = float(grupo["kwh_real"].sum())
                    kwh_esp_tot = float(grupo["kwh_esperado"].sum())
                    f_ini = grupo["fecha_turno"].iloc[0].strftime("%Y-%m-%d")
                    t_ini = int(grupo["turno"].iloc[0])
                    f_fin = grupo["fecha_turno"].iloc[-1].strftime("%Y-%m-%d")
                    t_fin = int(grupo["turno"].iloc[-1])

                    filas.append({
                        "id_alerta": f"SOST-{proc}-{f_ini}-T{t_ini}",
                        "fecha": f"{f_ini} al {f_fin}",
                        "fecha_fin": grupo["fecha_turno"].iloc[-1],
                        "fecha_inicio": grupo["fecha_turno"].iloc[0],
                        "turno": f"T{t_ini} → T{t_fin} ({len(grupo)} turnos)",
                        "proceso": proc,
                        "tipo": "Exceso sostenido",
                        "exceso_kwh": exceso_tot,
                        "costo_cop": costo_tot,
                        "kwh_real": kwh_real_tot,
                        "kwh_esperado": kwh_esp_tot,
                        "severidad": "media" if costo_tot < 250000 else "alta",
                        "confianza": conf,
                        "es_indicativa": es_baja,
                        "detalle": f"Racha de {len(grupo)} turnos seguidos superando el +{pct_umbral:.0f}% del consumo esperado."
                    })

    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).sort_values("costo_cop", ascending=False).reset_index(drop=True)


def obtener_alertas_anomalias_puntuales(
    df_res: pd.DataFrame,
    filtro_confianza: str = "firmes"  # "firmes", "indicativas", "todas"
) -> pd.DataFrame:
    """Alerta 2: Anomalías puntuales (es_anomalia == 1)."""
    filas = []
    anom = df_res[df_res["es_anomalia"] == 1].copy()

    for _, row in anom.iterrows():
        proc = str(row["proceso_modelo"])
        conf = str(row["confianza_modelo"])
        es_baja = (conf == "baja")

        if filtro_confianza == "firmes" and es_baja:
            continue
        if filtro_confianza == "indicativas" and not es_baja:
            continue

        f_str = row["fecha_turno"].strftime("%Y-%m-%d")
        t_int = int(row["turno"])
        costo = float(row.get("costo_exceso_cop", 0.0))
        exceso = float(row.get("exceso_kwh", 0.0))

        filas.append({
            "id_alerta": f"ANOM-{proc}-{f_str}-T{t_int}",
            "fecha": f_str,
            "fecha_fin": row["fecha_turno"],
            "fecha_inicio": row["fecha_turno"],
            "turno": f"Turno {t_int}",
            "proceso": proc,
            "tipo": "Anomalía puntual",
            "exceso_kwh": exceso,
            "costo_cop": costo,
            "kwh_real": float(row["kwh_real"]),
            "kwh_esperado": float(row["kwh_esperado"]),
            "severidad": str(row.get("severidad", "alta")),
            "confianza": conf,
            "es_indicativa": es_baja,
            "detalle": f"Marcada por detector estadístico (Isolation Forest + MAD). Puntaje: {float(row.get('puntaje_anomalia', 0.0)):.2f}"
        })

    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).sort_values("costo_cop", ascending=False).reset_index(drop=True)


def obtener_alertas_candidatas(
    df_cand: pd.DataFrame,
    tarifas_df: pd.DataFrame | None = None,
    tarifa_override: float | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Alertas 3a (Consumo en turno apagado) y 3b (Parada inesperada).

    Retorna: (df_turno_apagado, df_parada_inesperada)
    3a: z_robusto > 0 en una fila candidata del conjunto sintético.
    3b: z_robusto < 0 (ej. filtros con casi 0 kWh frente a 1,871 típicos).
    """
    if df_cand.empty:
        return pd.DataFrame(), pd.DataFrame()

    cand_3a = []
    cand_3b = []

    for _, row in df_cand.iterrows():
        proc = str(row["proceso"])
        f_dt = row["fecha_turno"]
        f_str = f_dt.strftime("%Y-%m-%d")
        t_int = int(row["turno"])
        kwh = float(row["kwh"])
        tipico = float(row["kwh_tipico"])
        z = float(row["z_robusto"])
        tarifa, _, _ = resolver_tarifa(f_dt, tarifas_df, tarifa_override)

        if z > 0:
            # 3a: Consumo en turno apagado
            exceso = max(kwh - tipico, 0.0)
            costo = exceso * tarifa
            cand_3a.append({
                "id_alerta": f"APAG-{proc}-{f_str}-T{t_int}",
                "fecha": f_str,
                "fecha_fin": f_dt,
                "fecha_inicio": f_dt,
                "turno": f"Turno {t_int}",
                "proceso": proc,
                "tipo": "Consumo en turno apagado",
                "exceso_kwh": exceso,
                "costo_cop": costo,
                "kwh_real": kwh,
                "kwh_esperado": tipico,
                "severidad": "media" if costo < 250000 else "alta",
                "confianza": "media" if proc == "triturado" else "baja",
                "es_indicativa": proc in ("refinacion", "filtros"),
                "detalle": f"Consumo de {kwh:,.1f} kWh vs {tipico:,.1f} kWh típico para este día/turno (z={z:.1f})."
            })
        else:
            # 3b: Parada inesperada
            deficit = max(tipico - kwh, 0.0)
            cand_3b.append({
                "id_alerta": f"PARADA-{proc}-{f_str}-T{t_int}",
                "fecha": f_str,
                "fecha_fin": f_dt,
                "fecha_inicio": f_dt,
                "turno": f"Turno {t_int}",
                "proceso": proc,
                "tipo": "Parada inesperada",
                "exceso_kwh": 0.0,
                "costo_cop": 0.0,
                "kwh_real": kwh,
                "kwh_esperado": tipico,
                "severidad": "baja",
                "confianza": "baja" if proc in ("refinacion", "filtros") else "media",
                "es_indicativa": proc in ("refinacion", "filtros"),
                "detalle": f"Consumo casi cero ({kwh:,.1f} kWh vs {tipico:,.1f} kWh típico). Posible parada no programada o festivo (z={z:.1f})."
            })

    df_3a = pd.DataFrame(cand_3a).sort_values("costo_cop", ascending=False).reset_index(drop=True) if cand_3a else pd.DataFrame()
    df_3b = pd.DataFrame(cand_3b).sort_values("exceso_kwh", ascending=False).reset_index(drop=True) if cand_3b else pd.DataFrame()
    return df_3a, df_3b


def obtener_avisos_calidad_turnos_incompletos(df_dm: pd.DataFrame) -> pd.DataFrame:
    """Alerta 4: Turnos con calidad_ok = 0 (cobertura < 75%).

    Es un aviso de calidad operativa, no una alerta de consumo excesivo.
    """
    incompletos = df_dm[df_dm["calidad_ok"] == 0].copy()
    if incompletos.empty:
        return pd.DataFrame()

    filas = []
    # Agrupar por fecha_turno y turno para consolidar los procesos afectados
    for (f_dt, turno), g in incompletos.groupby(["fecha_turno", "turno"]):
        procesos_afectados = ", ".join(sorted(g["proceso_modelo"].unique()))
        cob_prom = float(g["cobertura"].mean() * 100.0)
        f_str = f_dt.strftime("%Y-%m-%d")
        filas.append({
            "id_alerta": f"CAL-{f_str}-T{turno}",
            "fecha": f_str,
            "fecha_fin": f_dt,
            "fecha_inicio": f_dt,
            "turno": f"Turno {turno}",
            "proceso": procesos_afectados,
            "tipo": "Dato incompleto",
            "exceso_kwh": 0.0,
            "costo_cop": 0.0,
            "kwh_real": float(g["kwh"].sum()),
            "kwh_esperado": 0.0,
            "severidad": "informativa",
            "confianza": "N/A",
            "es_indicativa": False,
            "detalle": f"Cobertura inferior al 75% ({cob_prom:.1f}% válida). Turno excluido de modelos por calidad."
        })

    return pd.DataFrame(filas).sort_values("fecha_fin", ascending=False).reset_index(drop=True)
