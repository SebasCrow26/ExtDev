"""Screen 3.6: Refinery gas consumption and source data limits.

Daily SCADA series, telemetry quality, and separate monthly sintético history.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.datos import (
    get_base_mensual_gas_rc,
    get_config,
    get_dataset_modelo_dia,
    get_gas_dia,
)
from dashboard.estilos import configurar_grafico, render_callout, render_header


def render(filtros: dict):
    render_header(
        "Gas de refinación",
        "RC · Consumo diario y calidad del dato"
    )

    df_gas = get_gas_dia()
    df_dmd = get_dataset_modelo_dia()
    df_base_gas = get_base_mensual_gas_rc()
    cfg = get_config()

    df_gas["fecha"] = pd.to_datetime(df_gas["fecha"]).dt.normalize()
    fecha_min_datos = df_gas["fecha"].min().date()
    fecha_max_datos = df_gas["fecha"].max().date()
    with st.container(key="gas-filter-bar"):
        c_inicio, c_fin = st.columns(2)
        with c_inicio:
            fecha_inicio = st.date_input(
                "Fecha de inicio", value=fecha_min_datos,
                min_value=fecha_min_datos, max_value=fecha_max_datos,
                key="gas_fecha_inicio",
            )
        with c_fin:
            fecha_fin = st.date_input(
                "Fecha de fin", value=fecha_max_datos,
                min_value=fecha_min_datos, max_value=fecha_max_datos,
                key="gas_fecha_fin",
            )
    if fecha_inicio > fecha_fin:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        return
    df_gas = df_gas[
        (df_gas["fecha"].dt.date >= fecha_inicio)
        & (df_gas["fecha"].dt.date <= fecha_fin)
    ].copy()

    tarifa_gas = float(cfg.get("tarifas", {}).get("gas_cop_m3", 1500.0))

    render_callout(
        f"""
        > [!WARNING]
        > **Alcance y Limitación Declarada:**
        > El SCADA de gas disponible cubre **{(fecha_max_datos - fecha_min_datos).days + 1} días** ({fecha_min_datos:%d/%m/%Y} al {fecha_max_datos:%d/%m/%Y}).
        > **Las series de gas son sintéticas e independientes**; esta vista no realiza conciliación entre ellas.
        > Los conteos de días medidos, estimados y con reinicio se calculan desde la serie seleccionada.
        """
    )

    # Tarjetas métricas superiores
    tot_m3_medido = float(df_gas["m3"].sum())
    tot_costo_gas = tot_m3_medido * tarifa_gas
    dias_ok = int((df_gas["calidad"] == "ok").sum())
    dias_est = int((df_gas["calidad"] == "estimado").sum())
    dias_reinicio = int((df_gas["calidad"] == "reinicio").sum())

    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Consumo Total SCADA</span></div>
                <div class="kpi-value">{tot_m3_medido:,.1f} <span style="font-size:1rem;color:#94a3b8">m³</span></div>
                <div class="kpi-sub">{fecha_inicio:%d %b}–{fecha_fin:%d %b %Y} · {len(df_gas)} días con registro</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with g2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Costo Total Estimado</span></div>
                <div class="kpi-value" style="color:#212492">${tot_costo_gas:,.0f} <span style="font-size:0.9rem">COP</span></div>
                <div class="kpi-sub">Tarifa: ${tarifa_gas:,.2f} COP/m³</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with g3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Integridad de Datos</span></div>
                <div class="kpi-value" style="color:#10b981">{dias_ok} <span style="font-size:1rem">días OK</span></div>
                <div class="kpi-sub">{dias_est} estimados, {dias_reinicio} reinicios</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    st.markdown("---")

    # ==========================================================================
    # 1. SERIE DIARIA CON MARCAS DE CALIDAD
    # ==========================================================================
    st.markdown("### Consumo Diario de Gas con Estado de Telemetría")

    colores_calidad = {
        "ok": "#212492",
        "estimado": "#f59e0b",
        "reinicio": "#ef4444"
    }

    fig_gas = go.Figure()

    # Línea base de conexión
    fig_gas.add_trace(go.Scatter(
        x=df_gas["fecha"],
        y=df_gas["m3"],
        mode="lines",
        name="Consumo Diario (m³)",
        line={"color": "#64748b", "width": 1.5, "dash": "dot"},
        showlegend=False
    ))

    # Puntos coloreados por calidad
    for cal, color in colores_calidad.items():
        sub_cal = df_gas[df_gas["calidad"] == cal]
        if not sub_cal.empty:
            simbolo = "circle" if cal == "ok" else ("square" if cal == "estimado" else "triangle-up")
            etiqueta = "Medición Confiable (ok)" if cal == "ok" else ("Reparto Estimado" if cal == "estimado" else "Reinicio Contador (cota mínima)")
            costos = sub_cal["m3"] * tarifa_gas

            fig_gas.add_trace(go.Scatter(
                x=sub_cal["fecha"],
                y=sub_cal["m3"],
                mode="markers",
                name=etiqueta,
                marker={"color": color, "size": 8 if cal == "ok" else 11, "symbol": simbolo},
                customdata=costos,
                hovertemplate="<b>%{x|%d %b %Y}</b><br>Consumo: %{y:,.1f} m³<br>Costo: $%{customdata:,.0f} COP<br>Estado: " + cal + "<extra></extra>"
            ))

    fig_gas = configurar_grafico(fig_gas, "Consumo Diario de Gas de Refinación (m³ / día)", altura=380)
    fig_gas.update_yaxes(title_text="Gas (m³)")
    st.plotly_chart(fig_gas, use_container_width=True, theme=None)

    # ==========================================================================
    # 2. ULTIMOS SIETE DIAS DISPONIBLES
    # =======================================================================
    col_c1, col_c2 = st.columns([1, 1])
    fecha_ultimo_dato = pd.Timestamp(df_gas["fecha"].max()).normalize()
    fecha_inicio_7d = max(pd.Timestamp(fecha_inicio), fecha_ultimo_dato - pd.Timedelta(days=6))
    fechas_7d = pd.date_range(start=fecha_inicio_7d, end=fecha_ultimo_dato, freq="D")
    df_gas_7d = df_gas.copy()
    df_gas_7d["fecha"] = pd.to_datetime(df_gas_7d["fecha"]).dt.normalize()
    df_gas_7d = (
        df_gas_7d[df_gas_7d["fecha"].isin(fechas_7d)]
        .set_index("fecha").reindex(fechas_7d).rename_axis("fecha").reset_index()
    )
    df_gas_7d["calidad"] = df_gas_7d["calidad"].fillna("sin dato")

    with col_c1:
        st.markdown("#### Consumo de gas · últimos días del rango")
        colores_7d = ["#f5b82e" if fecha == fecha_ultimo_dato else "#212492" for fecha in df_gas_7d["fecha"]]
        fig_dias = go.Figure(go.Bar(
            x=df_gas_7d["fecha"],
            y=df_gas_7d["m3"],
            marker_color=colores_7d,
            customdata=df_gas_7d["calidad"],
            hovertemplate="%{x|%d %b %Y}<br>Consumo: %{y:,.1f} m³<br>Calidad: %{customdata}<extra></extra>",
            showlegend=False,
        ))
        fig_dias = configurar_grafico(fig_dias, "Consumo diario (m³)", altura=320)
        fig_dias.update_yaxes(title_text="m³")
        fig_dias.update_xaxes(tickformat="%d %b")
        st.plotly_chart(fig_dias, use_container_width=True, theme=None)
        st.caption(
            f"Amarillo: registro más reciente del rango ({fecha_ultimo_dato:%d %b %Y})."
        )

    with col_c2:
        st.markdown("#### Gas y energía de refinación · mismo periodo final")
        ref_d = df_dmd[df_dmd["proceso_modelo"] == "refinacion"][["fecha", "kwh"]].copy()
        ref_d["fecha"] = pd.to_datetime(ref_d["fecha"]).dt.normalize()
        ref_7d = pd.DataFrame({"fecha": fechas_7d}).merge(ref_d, on="fecha", how="left")
        serie = df_gas_7d[["fecha", "m3", "calidad"]].merge(ref_7d, on="fecha", how="left")
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Scatter(
            x=serie["fecha"], y=serie["m3"], name="Gas (m³)", mode="lines+markers",
            line={"color": "#36d8dc", "width": 2.5},
            marker={"color": ["#f5b82e" if f == fecha_ultimo_dato else "#36d8dc" for f in serie["fecha"]], "size": 8},
            customdata=serie["calidad"], yaxis="y",
            hovertemplate="%{x|%d %b %Y}<br>Gas: %{y:,.1f} m³<br>Calidad: %{customdata}<extra></extra>",
        ))
        fig_comp.add_trace(go.Scatter(
            x=serie["fecha"], y=serie["kwh"], name="Electricidad refinación (kWh)", mode="lines+markers",
            line={"color": "#8d68ff", "width": 2}, marker={"size": 6}, yaxis="y2",
            hovertemplate="%{x|%d %b %Y}<br>Electricidad: %{y:,.0f} kWh<extra></extra>",
        ))
        fig_comp = configurar_grafico(fig_comp, "Evolución diaria · gas y electricidad", altura=320)
        fig_comp.update_layout(
            yaxis={"title": "Gas (m³)", "gridcolor": "#252d49"},
            yaxis2={"title": "Electricidad (kWh)", "overlaying": "y", "side": "right", "showgrid": False},
            legend={"orientation": "h", "yanchor": "top", "y": -0.22, "xanchor": "center", "x": 0.5},
            margin={"l": 45, "r": 35, "t": 55, "b": 85},
        )
        fig_comp.update_xaxes(tickformat="%d %b")
        st.plotly_chart(fig_comp, use_container_width=True, theme=None)
    # 3. BASE MENSUAL HISTÓRICA DE CLARIOS (NO CONCILIABLE)
    # ==========================================================================
    st.markdown("---")
    st.markdown("### Serie mensual sintética de gas (referencia independiente)")
    render_callout(
        """
        > [!NOTE]
        > Esta serie mensual sintética es independiente de la serie diaria y solo ilustra el comportamiento del dashboard. No representa una conciliación operativa real.
        """
    )

    with st.expander("Ver serie mensual sintética de gas", expanded=False):
        df_base_view = df_base_gas.sort_values("mes", ascending=False).copy()
        df_base_view["Mes"] = df_base_view["mes"].dt.strftime("%Y-%m")
        df_base_view["Consumo (m³)"] = df_base_view["m3"].apply(lambda v: f"{v:,.1f}" if pd.notnull(v) else "-")
        df_base_view["Producción Eq."] = df_base_view["produccion_equivalente"].apply(lambda v: f"{v:,.1f}" if pd.notnull(v) else "-")
        df_base_view["m³ / eq."] = df_base_view["m3_por_eq"].apply(lambda v: f"{v:.3f}" if pd.notnull(v) else "-")
        df_base_view["Costo Total (COP)"] = df_base_view["costo_total_cop"].apply(lambda v: f"${v:,.0f}" if pd.notnull(v) else "-")

        st.dataframe(
            df_base_view[["Mes", "Consumo (m³)", "Producción Eq.", "m³ / eq.", "Costo Total (COP)"]],
            hide_index=True,
            use_container_width=True
        )

