"""detalle.py — Pantalla 3.2: Detalle por Proceso y Turno.

Series temporales de kWh real vs esperado, eje secundario de producción,
marcas de anomalías (es_anomalia=1), sombreado de turnos sin dato (calidad_ok=0),
exceso acumulado, mapa de calor día × turno y sección especial para F&A formación.
"""
from __future__ import annotations

import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dashboard.datos import (
    calcular_costo_kwh,
    get_anomalias_candidatas_rc,
    get_dataset_modelo,
    get_resultados_modelo,
    get_tarifa_kwh_mensual,
    resolver_tarifa,
)
from dashboard.estilos import (
    configurar_grafico,
    render_callout,
    render_header,
)
from dashboard.turnos import orden_turnos_cronologico


def render(filtros: dict):
    render_header(
        "Detalle por Proceso y Turno",
        "RC · Análisis energético del proceso"
    )

    df_res_todo = get_resultados_modelo()
    df_dm_todo = get_dataset_modelo()
    df_cand = get_anomalias_candidatas_rc()
    df_tarifas = get_tarifa_kwh_mensual()

    # Filtros propios de la página: periodo, planta, proceso y nivel temporal.
    c_ini, c_fin, c_planta = st.columns([1, 1, 1.35])
    with c_ini:
        f_ini = st.date_input(
            "Fecha de inicio", value=filtros["fecha_inicio"],
            min_value=datetime.date(2025, 10, 1), max_value=datetime.date(2026, 9, 30),
            key="detalle_fecha_inicio",
        )
    with c_fin:
        f_fin = st.date_input(
            "Fecha de fin", value=filtros["fecha_fin"],
            min_value=datetime.date(2025, 10, 1), max_value=datetime.date(2026, 9, 30),
            key="detalle_fecha_fin",
        )
    if f_ini > f_fin:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        return
    filtros = {**filtros, "fecha_inicio": f_ini, "fecha_fin": f_fin}

    with c_planta:
        planta_sel = st.selectbox(
            "Seleccionar Planta:",
            options=["RC (Procesos Principales)", "F&A (Formación)"],
            index=0,
            key="detalle_planta_sel"
        )

    if planta_sel.startswith("F&A"):
        render_fa_formacion(df_dm_todo, filtros)
        return

    # Estos controles solo aplican a los procesos RC; F&A tiene una vista
    # propia por turnos y no cuenta con modelo de exceso por proceso.
    c_proceso, c_nivel = st.columns([1.25, 1.5])
    procesos_rc = ["triturado", "horno", "refinacion", "filtros", "ptari"]
    with c_proceso:
        proc_sel = st.selectbox(
            "Proceso:",
            options=procesos_rc,
            index=0,
            format_func=lambda p: {
                "triturado": "Triturado",
                "horno": "Horno",
                "refinacion": "Refinación",
                "filtros": "Filtros",
                "ptari": "PTARI",
            }[p],
            key="detalle_proc_sel"
        )

    with c_nivel:
        nivel_agregacion = st.radio(
            "Mostrar por:",
            options=["Turno", "Día", "Semana"],
            index=0,
            horizontal=True,
            key="detalle_agregacion_sel"
        )

    # Filtrar datos de RC para el proceso
    df_p_res = df_res_todo[
        (df_res_todo["planta"] == "RC") &
        (df_res_todo["proceso_modelo"] == proc_sel) &
        (df_res_todo["fecha_turno"].dt.date >= f_ini) &
        (df_res_todo["fecha_turno"].dt.date <= f_fin)
    ].sort_values(["fecha_turno", "turno"]).copy()

    df_p_dm = df_dm_todo[
        (df_dm_todo["planta"] == "RC") &
        (df_dm_todo["proceso_modelo"] == proc_sel) &
        (df_dm_todo["fecha_turno"].dt.date >= f_ini) &
        (df_dm_todo["fecha_turno"].dt.date <= f_fin)
    ].sort_values(["fecha_turno", "turno"]).copy()

    if df_p_res.empty:
        st.warning(
            "La serie no tiene datos con esos filtros. El análisis de exceso y el mapa conservan sus propios filtros."
        )

    # Merge para tener cobertura, calidad_ok y producción
    df_merged = pd.merge(
        df_p_res,
        df_p_dm[["fecha_turno", "turno", "produccion", "cobertura", "calidad_ok"]],
        on=["fecha_turno", "turno"],
        how="right"  # Incluye turnos con calidad_ok = 0 que no están en resultados_modelo
    ).copy()
    orden_turno = orden_turnos_cronologico()
    df_merged["_orden_turno"] = df_merged["turno"].map(orden_turno)
    df_merged = df_merged.sort_values(["fecha_turno", "_orden_turno"]).drop(columns="_orden_turno").reset_index(drop=True)

    # Llenar valores nulos para turnos incompletos
    df_merged["calidad_ok"] = df_merged["calidad_ok"].fillna(0).astype(int)
    df_merged["cobertura"] = df_merged["cobertura"].fillna(0.0)
    df_merged["proceso_modelo"] = df_merged["proceso_modelo"].fillna(proc_sel)
    df_merged["confianza_modelo"] = df_merged["confianza_modelo"].fillna("baja")
    df_merged["es_anomalia"] = df_merged["es_anomalia"].fillna(0).astype(int)

    # Tarifa
    tarifa_val, _, _ = resolver_tarifa(pd.Timestamp(f_fin), df_tarifas, filtros.get("tarifa_override"))

    # Recalcular costo si viene nulo
    df_merged["costo_exceso_cop"] = df_merged["costo_exceso_cop"].fillna(
        np.maximum(df_merged["exceso_kwh"].fillna(0), 0) * tarifa_val
    )

    conf_proceso = df_merged["confianza_modelo"].iloc[0] if not df_merged.empty else None
    if conf_proceso == "baja":
        st.warning(f" **Confianza del modelo: BAJA.** Los excesos y predicciones de {proc_sel} tienen carácter **indicativo** y no constituyen una alarma operativa firme.")

    # ==========================================================================
    # 1. SERIE TEMPORAL REAL VS ESPERADO Y PRODUCCIÓN
    # ==========================================================================
    st.markdown(f"### Serie de Consumo y Producción — {proc_sel.capitalize()} ({nivel_agregacion})")

    if nivel_agregacion == "Turno":
        df_plot = df_merged.copy()
        df_plot["tiempo"] = df_plot["fecha_turno"].dt.strftime("%Y-%m-%d") + " T" + df_plot["turno"].astype(str)
        df_plot["fecha_eje"] = df_plot["fecha_turno"]
    elif nivel_agregacion == "Día":
        df_plot = df_merged.groupby("fecha_turno", as_index=False).agg({
            "kwh_real": "sum",
            "kwh_esperado": "sum",
            "exceso_kwh": "sum",
            "produccion": "sum",
            "costo_exceso_cop": "sum",
            "es_anomalia": "max",
            "calidad_ok": "min",
            "cobertura": "mean",
            "confianza_modelo": "first"
        })
        df_plot["tiempo"] = df_plot["fecha_turno"].dt.strftime("%Y-%m-%d")
        df_plot["fecha_eje"] = df_plot["fecha_turno"]
    else:  # Semana
        df_plot = df_merged.copy()
        df_plot["semana"] = df_plot["fecha_turno"].dt.to_period("W").apply(lambda r: r.start_time)
        df_plot = df_plot.groupby("semana", as_index=False).agg({
            "kwh_real": "sum",
            "kwh_esperado": "sum",
            "exceso_kwh": "sum",
            "produccion": "sum",
            "costo_exceso_cop": "sum",
            "es_anomalia": "max",
            "calidad_ok": "min",
            "cobertura": "mean",
            "confianza_modelo": "first"
        })
        df_plot["tiempo"] = df_plot["semana"].dt.strftime("Sem %Y-%m-%d")
        df_plot["fecha_eje"] = df_plot["semana"]

    colores_turno = {"1": "#35e6e6", "2": "#a78bfa", "3": "#fb7185"}
    if nivel_agregacion == "Turno":
        # Cuadrícula 2 × 2: comparación general y una comparación real/modelo por turno.
        def grafica_turno(datos: pd.DataFrame, titulo: str, comparar_todos: bool = False):
            fig = go.Figure()
            turnos_grafica = ("1", "2", "3") if comparar_todos else (
                (str(datos["turno"].iloc[0]),) if not datos.empty else ()
            )
            for turno_grafica in turnos_grafica:
                serie_grafica = datos[datos["turno"].astype(str) == turno_grafica].sort_values("fecha_eje")
                if serie_grafica.empty:
                    continue
                color = colores_turno[turno_grafica]
                fig.add_trace(go.Scatter(
                    x=serie_grafica["fecha_eje"], y=serie_grafica["kwh_real"],
                    mode="lines+markers", name=f"T{turno_grafica} real" if comparar_todos else "Real",
                    line={"color": color, "width": 2.5}, marker={"size": 4},
                    hovertemplate=f"T{turno_grafica} real · %{{x|%d %b}}: %{{y:,.1f}} kWh<extra></extra>",
                ))
                if not comparar_todos:
                    fig.add_trace(go.Scatter(
                        x=serie_grafica["fecha_eje"], y=serie_grafica["kwh_esperado"],
                        mode="lines", name="Esperado",
                        line={"color": "#cbd5e1", "width": 2, "dash": "dash"},
                        hovertemplate="Esperado: %{y:,.1f} kWh<extra></extra>",
                    ))
                incompletos_grafica = serie_grafica[serie_grafica["calidad_ok"] == 0]
                if not incompletos_grafica.empty:
                    fig.add_trace(go.Scatter(
                        x=incompletos_grafica["fecha_eje"], y=incompletos_grafica["kwh_real"].fillna(0),
                        mode="markers", showlegend=False, name="Dato incompleto",
                        marker={"size": 9, "color": "#64748b", "symbol": "x"},
                        hovertemplate="Dato incompleto · %{x|%d %b}<extra></extra>",
                    ))
                anomalias_grafica = serie_grafica[serie_grafica["es_anomalia"] == 1]
                if not anomalias_grafica.empty:
                    fig.add_trace(go.Scatter(
                        x=anomalias_grafica["fecha_eje"], y=anomalias_grafica["kwh_real"],
                        mode="markers", showlegend=False, name="Anomalía",
                        marker={"size": 10, "color": "#ff3c69", "symbol": "diamond-wide"},
                        hovertemplate="Anomalía · %{x|%d %b}<extra></extra>",
                    ))
            fig = configurar_grafico(fig, titulo, altura=330)
            fig.update_yaxes(title_text="Energía (kWh)", gridcolor="#252d49")
            fig.update_xaxes(tickformat="%d %b")
            fig.update_layout(
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
                margin={"t": 85, "b": 40, "l": 60, "r": 20},
            )
            return fig

        fila_superior = st.columns(2)
        with fila_superior[0]:
            st.plotly_chart(
                grafica_turno(df_plot, "Consumo real · T1, T2 y T3", comparar_todos=True),
                use_container_width=True, theme=None,
            )
        with fila_superior[1]:
            datos_t1 = df_plot[df_plot["turno"].astype(str) == "1"]
            st.plotly_chart(grafica_turno(datos_t1, "T1 · Real vs. esperado (06:00–14:00)"), use_container_width=True, theme=None)
        fila_inferior = st.columns(2)
        with fila_inferior[0]:
            datos_t2 = df_plot[df_plot["turno"].astype(str) == "2"]
            st.plotly_chart(grafica_turno(datos_t2, "T2 · Real vs. esperado (14:00–22:00)"), use_container_width=True, theme=None)
        with fila_inferior[1]:
            datos_t3 = df_plot[df_plot["turno"].astype(str) == "3"]
            st.plotly_chart(grafica_turno(datos_t3, "T3 · Real vs. esperado (22:00–06:00)"), use_container_width=True, theme=None)

    # Crear figura con 2 ejes Y
    fig_serie = make_subplots(specs=[[{"secondary_y": True}]])

    # Sombreado o puntos de datos incompletos
    incompletos = df_plot[df_plot["calidad_ok"] == 0]
    if not incompletos.empty:
        fig_serie.add_trace(
            go.Scatter(
                x=incompletos["fecha_eje"],
                y=incompletos["kwh_real"].fillna(0),
                mode="markers",
                name="Dato Incompleto (<75% cobertura)",
                marker={"size": 10, "color": "#64748b", "symbol": "x"},
                showlegend=False,
                hoverinfo="text",
                hovertext=[
                    f"Dato incompleto<br>Fecha: {t}<br>Cob: {c*100:.1f}%"
                    for t, c in zip(incompletos["tiempo"], incompletos["cobertura"])
                ]
            ),
            secondary_y=False
        )

    colores_turno = {"1": "#35e6e6", "2": "#a78bfa", "3": "#fb7185"}
    if nivel_agregacion == "Turno":
        # Separar las series por turno permite comparar su evolución diaria.
        for turno in ("1", "2", "3"):
            df_turno = df_plot[df_plot["turno"].astype(str) == turno].sort_values("fecha_turno")
            if df_turno.empty:
                continue
            color = colores_turno[turno]
            customdata = np.stack((
                df_turno["kwh_esperado"].fillna(0),
                df_turno["exceso_kwh"].fillna(0),
                df_turno["costo_exceso_cop"].fillna(0),
                df_turno["confianza_modelo"].fillna("N/A"),
                df_turno["cobertura"].fillna(0) * 100.0,
                df_turno["produccion"].fillna(0)
            ), axis=-1)
            fig_serie.add_trace(
                go.Scatter(
                x=df_turno["fecha_eje"], y=df_turno["kwh_real"],
                    mode="lines+markers", name=f"T{turno} · Real",
                    line={"color": color, "width": 2.5}, marker={"size": 4},
                    customdata=customdata,
                    hovertemplate=(
                        "<b>%{x|%d %b %Y} · T" + turno + "</b><br>"
                        "Real: %{y:,.1f} kWh<br>Esperado: %{customdata[0]:,.1f} kWh<br>"
                        "Exceso: %{customdata[1]:+,.1f} kWh<br>"
                        "Costo exceso: $%{customdata[2]:,.0f} COP<br>"
                        "Confianza: %{customdata[3]}<br>Cobertura: %{customdata[4]:.1f}%<br>"
                        "Producción: %{customdata[5]:,.0f} kg<extra></extra>"
                    )
                ), secondary_y=False
            )
            fig_serie.add_trace(
                go.Scatter(
                    x=df_turno["fecha_eje"], y=df_turno["kwh_esperado"],
                    mode="lines", name=f"T{turno} · Esperado",
                    line={"color": color, "width": 1.5, "dash": "dash"},
                    hovertemplate=f"T{turno} esperado: %{{y:,.1f}} kWh<extra></extra>"
                ), secondary_y=False
            )
    else:
        # En las vistas agregadas, conservar las series totales por día o semana.
        fig_serie.add_trace(
            go.Scatter(
                x=df_plot["fecha_eje"], y=df_plot["kwh_real"],
                mode="lines+markers", name="kWh Real",
                line={"color": "#35e6e6", "width": 2.5}, marker={"size": 4},
                customdata=np.stack((
                    df_plot["kwh_esperado"].fillna(0), df_plot["exceso_kwh"].fillna(0),
                    df_plot["costo_exceso_cop"].fillna(0), df_plot["confianza_modelo"].fillna("N/A"),
                    df_plot["cobertura"].fillna(0) * 100.0, df_plot["produccion"].fillna(0)
                ), axis=-1),
                hovertemplate=(
                    "<b>%{x}</b><br>Real: %{y:,.1f} kWh<br>Esperado: %{customdata[0]:,.1f} kWh<br>"
                    "Exceso: %{customdata[1]:+,.1f} kWh<br>Costo exceso: $%{customdata[2]:,.0f} COP<br>"
                    "Confianza: %{customdata[3]}<br>Cobertura: %{customdata[4]:.1f}%<br>"
                    "Producción: %{customdata[5]:,.0f} kg<extra></extra>"
                )
            ), secondary_y=False
        )
        fig_serie.add_trace(
            go.Scatter(
                x=df_plot["fecha_eje"], y=df_plot["kwh_esperado"], mode="lines",
                name="kWh Esperado (Modelo)",
                line={"color": "#9a6cff", "width": 2, "dash": "dash"},
                hovertemplate="Esperado: %{y:,.1f} kWh<extra></extra>"
            ), secondary_y=False
        )

    # Anomalías puntuales
    anomalias = df_plot[df_plot["es_anomalia"] == 1]
    if not anomalias.empty:
        fig_serie.add_trace(
            go.Scatter(
                x=anomalias["fecha_eje"],
                y=anomalias["kwh_real"],
                mode="markers",
                name="Anomalía Puntual (es_anomalia=1)",
                marker={"size": 12, "color": "#ff3c69", "symbol": "diamond-wide"},
                hovertemplate="<b>Anomalía Puntual</b><br>Consumo real: %{y:,.1f} kWh<extra></extra>"
            ),
            secondary_y=False
        )

    titulo_serie = "Consumo por turno: real vs. esperado" if nivel_agregacion == "Turno" else "Consumo de Energía: kWh Real vs. kWh Esperado"
    altura_serie = 500 if nivel_agregacion == "Turno" else 400
    fig_serie = configurar_grafico(fig_serie, titulo_serie, altura=altura_serie)
    fig_serie.update_yaxes(title_text="Energía (kWh)", secondary_y=False, gridcolor="#252d49")
    fig_serie.update_xaxes(tickformat="%d %b")
    if nivel_agregacion == "Turno":
        # Ubicar las seis series en una leyenda propia debajo de la gráfica.
        fig_serie.update_layout(
            legend={"orientation": "h", "yanchor": "top", "y": -0.2, "xanchor": "left", "x": 0},
            margin={"t": 85, "b": 110, "l": 65, "r": 30},
        )
    if nivel_agregacion != "Turno":
        st.plotly_chart(fig_serie, use_container_width=True, theme=None)

    # ==========================================================================
    # 2. ANALISIS DEL EXCESO ACUMULADO
    # =======================================================================
    st.markdown("### An\u00e1lisis de Exceso Energ\u00e9tico")
    fecha_max_exceso = df_res_todo["fecha_turno"].max().date()
    fecha_min_exceso = df_res_todo["fecha_turno"].min().date()
    rango_default_exceso = (
        max(fecha_min_exceso, fecha_max_exceso - datetime.timedelta(days=29)),
        fecha_max_exceso,
    )
    c_exceso_ini, c_exceso_fin, c_exceso_proceso = st.columns([1, 1, 1])
    with c_exceso_ini:
        f_exceso_ini = st.date_input(
            "Fecha de inicio · análisis de exceso",
            value=rango_default_exceso[0], min_value=fecha_min_exceso,
            max_value=fecha_max_exceso, key="detalle_exceso_fecha_inicio",
        )
    with c_exceso_fin:
        f_exceso_fin = st.date_input(
            "Fecha de fin · análisis de exceso",
            value=rango_default_exceso[1], min_value=fecha_min_exceso,
            max_value=fecha_max_exceso, key="detalle_exceso_fecha_fin",
        )
    with c_exceso_proceso:
        proceso_exceso = st.selectbox(
            "Proceso para exceso y mapa",
            options=procesos_rc,
            index=0,
            format_func=lambda p: {
                "triturado": "Triturado",
                "horno": "Horno",
                "refinacion": "Refinaci\u00f3n",
                "filtros": "Filtros",
                "ptari": "PTARI",
            }[p],
            key="detalle_proceso_exceso",
        )
    if f_exceso_ini > f_exceso_fin:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        return
    tarifa_exceso, _, _ = resolver_tarifa(
        pd.Timestamp(f_exceso_fin), df_tarifas, filtros.get("tarifa_override")
    )
    res_exceso = df_res_todo[
        (df_res_todo["planta"] == "RC")
        & (df_res_todo["proceso_modelo"] == proceso_exceso)
        & (df_res_todo["fecha_turno"].dt.date >= f_exceso_ini)
        & (df_res_todo["fecha_turno"].dt.date <= f_exceso_fin)
    ].copy()
    dm_exceso = df_dm_todo[
        (df_dm_todo["planta"] == "RC")
        & (df_dm_todo["proceso_modelo"] == proceso_exceso)
        & (df_dm_todo["fecha_turno"].dt.date >= f_exceso_ini)
        & (df_dm_todo["fecha_turno"].dt.date <= f_exceso_fin)
    ].copy()
    df_analisis = pd.merge(
        res_exceso,
        dm_exceso[["fecha_turno", "turno", "produccion", "cobertura", "calidad_ok"]],
        on=["fecha_turno", "turno"],
        how="right",
    )
    df_acum = df_analisis.dropna(subset=["exceso_kwh"]).copy()
    if not df_acum.empty:
        diario = (
            df_acum.groupby("fecha_turno", as_index=False)
            .agg(exceso_kwh=("exceso_kwh", "sum"))
            .sort_values("fecha_turno")
        )
        diario["exceso_acum_kwh"] = diario["exceso_kwh"].cumsum()
        diario["costo_acum_cop"] = diario["exceso_acum_kwh"] * tarifa_exceso
        exceso_final = float(diario["exceso_acum_kwh"].iloc[-1])
        costo_final = float(diario["costo_acum_cop"].iloc[-1])
        costo_final_texto = f"{'+' if costo_final >= 0 else '-'}${abs(costo_final):,.0f} COP"
        metrica_exceso, metrica_costo = st.columns([1, 1])
        with metrica_exceso:
            st.markdown(
                f'<div class="detalle-kpi"><span>Exceso neto acumulado</span>'
                f'<strong class="exceso">{exceso_final:+,.0f} kWh</strong></div>',
                unsafe_allow_html=True,
            )
        with metrica_costo:
            st.markdown(
                f'<div class="detalle-kpi"><span>Costo estimado acumulado</span>'
                f'<strong class="costo">{costo_final_texto}</strong></div>',
                unsafe_allow_html=True,
            )

        fig_acum = go.Figure()
        fig_acum.add_trace(go.Scatter(
            x=diario["fecha_turno"],
            y=diario["exceso_acum_kwh"],
            mode="lines",
            name="Exceso acumulado",
            line={"color": "#ff3c69", "width": 2.5},
            fill="tozeroy",
            fillcolor="rgba(255, 60, 105, 0.15)",
            customdata=diario["costo_acum_cop"],
            hovertemplate="<b>%{x|%d %b %Y}</b><br>Exceso acumulado: %{y:+,.1f} kWh<br>Costo estimado: $%{customdata:+,.0f} COP<extra></extra>",
        ))
        fig_acum.add_hline(y=0, line_dash="solid", line_color="#36d8dc", line_width=1)
        fig_acum = configurar_grafico(fig_acum, "Trayectoria del exceso acumulado", altura=350)
        fig_acum.update_yaxes(title_text="Exceso acumulado (kWh)")
        fig_acum.update_xaxes(title_text="Fecha", tickformat="%d %b")
        st.plotly_chart(fig_acum, use_container_width=True, theme=None)
    else:
        st.info("No hay datos de exceso para graficar en el periodo seleccionado.")

    # =======================================================================
    # 3. MAPA DE CALOR DEL EXCESO POR DIA Y TURNO
    # =======================================================================
    st.markdown("### Mapa de calor del exceso (D\u00eda x Turno)")
    st.caption("Escala divergente centrada en cero: verde es d\u00e9ficit y magenta es exceso.")
    df_hm = df_analisis.dropna(subset=["exceso_kwh"]).copy()
    if not df_hm.empty:
        df_hm["dia_str"] = df_hm["fecha_turno"].dt.strftime("%Y-%m-%d")
        df_hm["turno_label"] = "T" + df_hm["turno"].astype(str)
        pivot_hm = df_hm.pivot_table(
            index="turno_label",
            columns="dia_str",
            values="exceso_kwh",
            aggfunc="sum",
        )
        if not pivot_hm.empty:
            max_abs = float(np.nanmax(np.abs(pivot_hm.to_numpy(dtype=float))))
            if not np.isfinite(max_abs) or max_abs == 0:
                max_abs = 100
            orden_filas = [f"T{t}" for t in orden_turnos_cronologico()]
            pivot_hm = pivot_hm.reindex([t for t in orden_filas if t in pivot_hm.index])
            fig_hm = px.imshow(
                pivot_hm,
                color_continuous_scale=[
                    [0.0, "#008f78"],
                    [0.42, "#143d47"],
                    [0.5, "#192036"],
                    [0.58, "#57263d"],
                    [1.0, "#ff3c69"],
                ],
                range_color=[-max_abs, max_abs],
                labels={"color": "Exceso (kWh)"},
                aspect="auto",
            )
            fig_hm = configurar_grafico(fig_hm, "Exceso por d\u00eda y turno (kWh)", altura=340)
            fig_hm.update_traces(xgap=3, ygap=3, hoverongaps=False)
            meses_es = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
            dias_ticks = list(pivot_hm.columns[::max(1, len(pivot_hm.columns) // 12)])
            etiquetas_ticks = [
                f"{fecha.day} {meses_es[fecha.month - 1]}"
                for fecha in pd.to_datetime(dias_ticks)
            ]
            fig_hm.update_xaxes(title_text="Día", tickmode="array", tickvals=dias_ticks, ticktext=etiquetas_ticks)
            fig_hm.update_yaxes(title_text="Turno")
            st.plotly_chart(fig_hm, use_container_width=True, theme=None)
    else:
        st.info("No hay datos de exceso para construir el mapa de calor en el periodo seleccionado.")
# ==============================================================================

def render_fa_formacion(df_dm_todo: pd.DataFrame, filtros: dict):
    """Renderiza el análisis exclusivo para F&A Formación.

    Reglas exactas:
    - F&A no está en resultados_modelo.
    - Muestra dataset_modelo (planta F&A): kWh por turno, unidades y patrón encendido/apagado.
    - Solo hay de julio a septiembre de 2026.
    - NUNCA muestra exceso de F&A.
    """
    st.info(
        "**Planta F&A — Proceso de Formación:** F&A no cuenta con modelo de consumo esperado en `resultados_modelo` "
        "(la serie es ilustrativa y su comportamiento depende de los datos sintéticos incluidos). "
        "Se presenta el consumo real, unidades producidas y el patrón de turnos activos. **No se calculan excesos para F&A.**"
    )

    orden_turno = orden_turnos_cronologico()
    df_fa = df_dm_todo[df_dm_todo["planta"] == "F&A"].copy()
    df_fa["_orden_turno"] = df_fa["turno"].map(orden_turno)
    df_fa = df_fa.sort_values(["fecha_turno", "_orden_turno"]).drop(columns="_orden_turno")

    # Filtro global de fechas
    f_ini, f_fin = filtros["fecha_inicio"], filtros["fecha_fin"]
    df_fa_show = df_fa[
        (df_fa["fecha_turno"].dt.date >= f_ini) &
        (df_fa["fecha_turno"].dt.date <= f_fin)
    ].copy()

    if df_fa_show.empty:
        st.warning("No hay registros de F&A en el rango seleccionado (disponible julio a septiembre de 2026).")
        return

    # Tarjetas KPI de F&A
    tot_kwh_fa = float(df_fa_show["kwh"].sum())
    tot_unidades_fa = float(df_fa_show["produccion"].sum())
    intensidad_fa = (tot_kwh_fa / tot_unidades_fa) if tot_unidades_fa > 0 else 0.0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Consumo F&A Formación</span></div>
                <div class="kpi-value">{tot_kwh_fa:,.0f} <span style="font-size:1rem;color:#94a3b8">kWh</span></div>
                <div class="kpi-sub">3 rectificadores acumulados</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with k2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Unidades Producidas</span></div>
                <div class="kpi-value">{tot_unidades_fa:,.0f} <span style="font-size:1rem;color:#94a3b8">unidades</span></div>
                <div class="kpi-sub">Línea FAFORM02</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with k3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Intensidad Real</span></div>
                <div class="kpi-value">{intensidad_fa:.2f} <span style="font-size:1rem;color:#94a3b8">kWh/u</span></div>
                <div class="kpi-sub">Indicador de la serie sintética</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with k4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Alcance de datos</span></div>
                <div class="kpi-value" style="font-size:1.2rem;color:#fcd34d;">Sintético</div>
                <div class="kpi-sub">Sin referencia operativa real</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Serie diaria de consumo: una línea por cada uno de los tres turnos.
    st.markdown("#### Serie por Turno de Formación (F&A)")
    colores_turno = {"T1": "#22d3ee", "T2": "#a78bfa", "T3": "#fb7185"}
    fig_fa = go.Figure()
    for turno in ("T1", "T2", "T3"):
        numero_turno = turno[1:]
        df_turno = df_fa_show[df_fa_show["turno"].astype(str) == numero_turno].sort_values("fecha_turno")
        if df_turno.empty:
            continue
        fig_fa.add_trace(
            go.Scatter(
                x=df_turno["fecha_turno"],
                y=df_turno["kwh"],
                mode="lines+markers",
                name=f"{turno} · { {'T1': '06:00–14:00', 'T2': '14:00–22:00', 'T3': '22:00–06:00'}[turno] }",
                line={"color": colores_turno[turno], "width": 2},
                marker={"size": 5},
                connectgaps=False,
            )
        )
    fig_fa = configurar_grafico(fig_fa, "Consumo diario por turno — F&A Formación", altura=400)
    fig_fa.update_yaxes(title_text="Consumo (kWh)")
    fig_fa.update_xaxes(title_text="Fecha", tickformat="%d %b")
    st.plotly_chart(fig_fa, use_container_width=True, theme=None)

    # Patrón encendido / apagado
    st.markdown("#### Patrón de Encendido / Apagado Semanal")
    render_callout("Los gráficos de F&A usan exclusivamente datos sintéticos y muestran patrones de demostración. No son un calendario ni una medición operativa real.")
