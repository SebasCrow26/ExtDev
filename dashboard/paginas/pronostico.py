"""pronostico.py — Pantalla 3.4: Pronóstico y Simulación de Escenarios.

Simulación del plan operativo por proceso,
escenario, día y turno.
"""
from __future__ import annotations

import datetime
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dashboard.datos import (
    get_dataset_modelo,
    get_dataset_modelo_dia,
    get_tarifa_kwh_mensual,
    resolver_tarifa,
)
from dashboard.estilos import configurar_grafico, render_header
from modelos.modelo_esperado_api import predecir

ETIQUETAS_PROCESO = {
    "horno": "Horno",
    "triturado": "Triturado",
    "refinacion": "Refinación",
    "filtros": "Filtros",
    "ptari": "PTARI",
}


def render(filtros: dict):
    render_header(
        "Pronóstico y Escenarios",
        "RC · Proyección de consumo y simulación"
    )

    df_tarifas = get_tarifa_kwh_mensual()

    procesos_rc = ["horno", "triturado", "refinacion", "filtros", "ptari"]

    st.markdown(
        """
        <div class="method-banner">
            <strong>SIMULACIÓN OPERATIVA · PLAN DE PRODUCCIÓN</strong><br>
            Ingresa el plan que la empresa quiere evaluar. Los valores precargados son referencias del mismo día de
            semana y turno de las últimas cuatro semanas. Los escenarios ajustan el plan: bajo 0,85 · base 1,00 · alto
            1,15. El consumo se estima con el modelo y sus datos históricos.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Simulación del plan de producción")
    st.caption(
        "Ingresa las cantidades planeadas. Los valores precargados son referencias históricas editables; "
        "la simulación utiliza el modelo de consumo y su intervalo de incertidumbre."
    )

    ctrl1, ctrl2, ctrl3 = st.columns([1.1, 1, 1.5])
    with ctrl1:
        sim_proceso = st.selectbox(
            "Proceso",
            options=procesos_rc,
            format_func=lambda proceso: ETIQUETAS_PROCESO.get(proceso, proceso.capitalize()),
            key="sim_proc_choice",
        )
    with ctrl2:
        nivel_sim = st.selectbox(
            "Nivel de agregación",
            options=["Semana", "Día"],
            key="sim_nivel_choice",
        )
    with ctrl3:
        escenario_sim = st.radio(
            "Escenario de producción",
            options=["Base", "Bajo", "Alto"],
            horizontal=True,
            key="sim_escenario_choice",
        )

    fecha_sim = st.date_input(
        "Fecha de operación" if nivel_sim == "Día" else "Fecha inicial del plan",
        value=datetime.date.today(),
        key="sim_fecha_choice_v2",
        help="En nivel semana se simulan esta fecha y los seis días siguientes.",
    )
    factor_escenario = {"Bajo": 0.85, "Base": 1.0, "Alto": 1.15}[escenario_sim]

    df_hist_turno = get_dataset_modelo()
    df_hist_dia = get_dataset_modelo_dia()
    proceso_hist_turno = df_hist_turno[
        (df_hist_turno["planta"] == "RC") & (df_hist_turno["proceso_modelo"] == sim_proceso)
    ].copy()
    proceso_hist_dia = df_hist_dia[
        (df_hist_dia["planta"] == "RC") & (df_hist_dia["proceso_modelo"] == sim_proceso)
    ].copy()
    if not proceso_hist_turno.empty:
        proceso_hist_turno["fecha_turno"] = pd.to_datetime(proceso_hist_turno["fecha_turno"])
    if not proceso_hist_dia.empty:
        proceso_hist_dia["fecha"] = pd.to_datetime(proceso_hist_dia["fecha"])

    dias_es = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

    def produccion_historica_dia(fecha: datetime.date) -> float:
        if proceso_hist_dia.empty:
            return 0.0
        hist = proceso_hist_dia[
            (proceso_hist_dia["fecha"].dt.dayofweek == fecha.weekday())
            & (proceso_hist_dia["fecha"].dt.date < fecha)
        ].sort_values("fecha").tail(4)
        if hist.empty:
            return 0.0
        return float(hist["produccion"].mean())

    submitted = False
    if nivel_sim == "Día":
        st.markdown("#### Producción planeada por turno")
        st.caption("Turno 1: 06:00–14:00 · Turno 2: 14:00–22:00 · Turno 3: 22:00–06:00")
        turno_cols = st.columns(3)
        produccion_turnos = {}
        for turno, columna in zip((1, 2, 3), turno_cols):
            ref = 0.0
            if not proceso_hist_turno.empty:
                mismo_turno = proceso_hist_turno[
                    (proceso_hist_turno["turno"] == turno)
                    & (proceso_hist_turno["fecha_turno"].dt.dayofweek == fecha_sim.weekday())
                    & (proceso_hist_turno["fecha_turno"].dt.date < fecha_sim)
                ].sort_values("fecha_turno").tail(4)
                if not mismo_turno.empty:
                    ref = float(mismo_turno["produccion"].mean())
            with columna:
                produccion_turnos[turno] = st.number_input(
                    f"Turno {turno} · producción (kg)",
                    min_value=0.0,
                    max_value=300000.0,
                    value=float(round(ref, 0)),
                    step=1000.0,
                    key=f"sim_prod_turno_{turno}_v2",
                    help="Valor precargado: promedio reciente del mismo turno y día de semana.",
                )
        submitted = st.button("Calcular escenario", type="primary", key="sim_calcular_dia_v2")
        fechas_plan = [fecha_sim]
        producciones_base = [sum(produccion_turnos.values())]
        detalle_turnos = produccion_turnos
    else:
        fecha_inicio_semana = fecha_sim
        st.caption(
            f"Plan diario para los siete días {fecha_inicio_semana:%d/%m/%Y}–"
            f"{(fecha_inicio_semana + datetime.timedelta(days=6)):%d/%m/%Y}. "
            "Los datos precargados son promedios recientes por día de semana; edítalos con el plan aprobado."
        )
        fechas_plan = [fecha_inicio_semana + datetime.timedelta(days=i) for i in range(7)]
        producciones_base = [0.0] * 7
        for fila_inicio in (0, 4):
            cols = st.columns(4)
            for idx in range(fila_inicio, min(fila_inicio + 4, 7)):
                fecha_dia = fechas_plan[idx]
                with cols[idx - fila_inicio]:
                    prod_ref = produccion_historica_dia(fecha_dia)
                    producciones_base[idx] = st.number_input(
                        f"{dias_es[fecha_dia.weekday()]} {fecha_dia:%d/%m} (kg)",
                        min_value=0.0,
                        max_value=300000.0,
                        value=float(round(prod_ref, 0)),
                        step=1000.0,
                        key=f"sim_prod_dia_{idx}_v2",
                    )
        detalle_turnos = None
        submitted = st.button("Calcular escenario semanal", type="primary", key="sim_calcular_semana_v2")

    if submitted:
        try:
            resultados = []
            if nivel_sim == "Día":
                # El T1 cruza medianoche; en la fecha de turno, T2 y T3 ocurren antes que T1.
                orden_cronologico = (2, 3, 1)
                historial = proceso_hist_turno[
                    proceso_hist_turno["fecha_turno"].dt.date < fecha_sim
                ].copy()
                historial["orden"] = historial["turno"].map({2: 0, 3: 1, 1: 2})
                historial = historial.sort_values(["fecha_turno", "orden"])
                rezagos = historial["produccion"].tail(2).astype(float).tolist()
                rezagos = [0.0] * (2 - len(rezagos)) + rezagos
                kwh_esp = kwh_inf = kwh_sup = 0.0
                for turno in orden_cronologico:
                    produccion_ajustada = float(detalle_turnos[turno]) * factor_escenario
                    pred_turno = predecir(
                        proceso=sim_proceso,
                        produccion=produccion_ajustada,
                        planta="RC",
                        nivel="turno",
                        fecha=str(fecha_sim),
                        turno=turno,
                        produccion_t1=rezagos[-1],
                        produccion_t2=rezagos[-2],
                    )
                    resultados.append({
                        "Fecha": fecha_sim.strftime("%Y-%m-%d"),
                        "Día": dias_es[fecha_sim.weekday()],
                        "Turno": f"T{turno}",
                        "Producción plan (kg)": detalle_turnos[turno],
                        "Producción escenario (kg)": round(produccion_ajustada, 1),
                        "kWh inferior": pred_turno["kwh_inferior"],
                        "kWh pronosticado": pred_turno["kwh_esperado"],
                        "kWh superior": pred_turno["kwh_superior"],
                        "Costo estimado (COP)": round(
                            pred_turno["kwh_esperado"] * resolver_tarifa(
                                str(fecha_sim), df_tarifas, filtros.get("tarifa_override")
                            )[0], 0
                        ),
                    })
                    kwh_inf += pred_turno["kwh_inferior"]
                    kwh_esp += pred_turno["kwh_esperado"]
                    kwh_sup += pred_turno["kwh_superior"]
                    rezagos = [rezagos[-1], produccion_ajustada]
                modelo_nombre = pred_turno.get("modelo", "Modelo por turno")
                nota_intervalo = "Suma de intervalos por turno; rango orientativo para el día."
            else:
                historial = proceso_hist_dia[
                    proceso_hist_dia["fecha"].dt.date < fechas_plan[0]
                ].sort_values("fecha")
                rezagos = historial["produccion"].tail(2).astype(float).tolist()
                rezagos = [0.0] * (2 - len(rezagos)) + rezagos
                kwh_inf = kwh_esp = kwh_sup = 0.0
                for fecha_dia, prod_base in zip(fechas_plan, producciones_base):
                    prod_ajustada = float(prod_base) * factor_escenario
                    pred_dia = predecir(
                        proceso=sim_proceso,
                        produccion=prod_ajustada,
                        planta="RC",
                        nivel="dia",
                        fecha=str(fecha_dia),
                        produccion_t1=rezagos[-1],
                        produccion_t2=rezagos[-2],
                    )
                    tarifa_dia, _, _ = resolver_tarifa(
                        str(fecha_dia), df_tarifas, filtros.get("tarifa_override")
                    )
                    resultados.append({
                        "Fecha": fecha_dia.strftime("%Y-%m-%d"),
                        "Día": dias_es[fecha_dia.weekday()],
                        "Producción plan (kg)": round(float(prod_base), 1),
                        "Producción escenario (kg)": round(prod_ajustada, 1),
                        "kWh inferior": pred_dia["kwh_inferior"],
                        "kWh pronosticado": pred_dia["kwh_esperado"],
                        "kWh superior": pred_dia["kwh_superior"],
                        "Costo estimado (COP)": round(pred_dia["kwh_esperado"] * tarifa_dia, 0),
                    })
                    kwh_inf += pred_dia["kwh_inferior"]
                    kwh_esp += pred_dia["kwh_esperado"]
                    kwh_sup += pred_dia["kwh_superior"]
                    rezagos = [rezagos[-1], prod_ajustada]
                modelo_nombre = pred_dia.get("modelo", "Modelo diario")
                nota_intervalo = "Suma de intervalos diarios; rango orientativo para la semana."

            produccion_total = sum(float(v) for v in producciones_base)
            costo_total = sum(float(fila["Costo estimado (COP)"]) for fila in resultados)
            st.markdown("#### Resultado del plan")
            st.markdown(
                f"""
                <div class="pron-result-grid">
                    <div class="pron-result-card"><small>Producción del plan</small><strong>{produccion_total:,.0f} <i>kg</i></strong></div>
                    <div class="pron-result-card"><small>Producción escenario</small><strong>{produccion_total * factor_escenario:,.0f} <i>kg</i></strong></div>
                    <div class="pron-result-card"><small>Consumo estimado</small><strong>{kwh_esp:,.0f} <i>kWh</i></strong></div>
                    <div class="pron-result-card"><small>Costo estimado</small><strong>${costo_total:,.0f} <i>COP</i></strong></div>
                </div>
                <div class="pron-result-meta">
                    Intervalo estimado: {kwh_inf:,.0f}–{kwh_sup:,.0f} kWh
                    · Modelo: {modelo_nombre.upper()} · Escenario: {escenario_sim} (factor {factor_escenario:.2f})
                </div>
                <div class="pron-result-note">{nota_intervalo}</div>
                """,
                unsafe_allow_html=True,
            )
            df_resultados = pd.DataFrame(resultados)
            eje_x = "Turno" if nivel_sim == "Día" else "Fecha"
            fig_plan = make_subplots(specs=[[{"secondary_y": True}]])
            fig_plan.add_trace(
                go.Scatter(
                    x=df_resultados[eje_x],
                    y=df_resultados["kWh superior"],
                    mode="lines",
                    line={"width": 0},
                    showlegend=False,
                    hoverinfo="skip",
                ),
                secondary_y=False,
            )
            fig_plan.add_trace(
                go.Scatter(
                    x=df_resultados[eje_x],
                    y=df_resultados["kWh inferior"],
                    mode="lines",
                    line={"width": 0},
                    fill="tonexty",
                    fillcolor="rgba(141, 104, 255, 0.18)",
                    name="Intervalo del modelo",
                ),
                secondary_y=False,
            )
            fig_plan.add_trace(
                go.Scatter(
                    x=df_resultados[eje_x],
                    y=df_resultados["kWh pronosticado"],
                    mode="lines+markers",
                    name="Consumo esperado",
                    line={"color": "#36d8dc", "width": 3},
                    marker={"size": 7},
                ),
                secondary_y=False,
            )
            fig_plan.add_trace(
                go.Bar(
                    x=df_resultados[eje_x],
                    y=df_resultados["Producción escenario (kg)"],
                    name="Producción del escenario",
                    marker_color="rgba(27, 198, 160, 0.32)",
                    marker_line_color="#1bc6a0",
                    marker_line_width=1,
                ),
                secondary_y=True,
            )
            titulo_eje = "kWh por turno" if nivel_sim == "Día" else "kWh por día"
            unidad_prod = "kg por turno" if nivel_sim == "Día" else "kg por día"
            fig_plan = configurar_grafico(
                fig_plan,
                f"Consumo previsto según el plan · {ETIQUETAS_PROCESO[sim_proceso]} · {escenario_sim}",
                altura=350,
            )
            fig_plan.update_yaxes(title_text=titulo_eje, secondary_y=False)
            fig_plan.update_yaxes(title_text=unidad_prod, secondary_y=True, showgrid=False)
            st.plotly_chart(fig_plan, use_container_width=True, theme=None)
            st.dataframe(df_resultados, hide_index=True, use_container_width=True)
        except FileNotFoundError as e:
            st.error(str(e))
            st.info("Verifica que exista `modelos/modelos.pkl` en la raíz del repositorio.")
        except Exception as e:
            st.error(f"No fue posible calcular el escenario: {e}")

