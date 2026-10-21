"""calidad.py — Pantalla 3.7: Calidad de Datos, Conciliación y Supuestos.

Auditoría de telemetría SCADA (horas sintéticas por medidor),
reinicios de contadores (eventos sintéticos), congelamientos (duración máxima dinámica),
razón de energía con la base esta demostración (mediana 0.62) y catálogo de los 10 supuestos clave.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.datos import (
    get_calidad_energia_fa,
    get_calidad_energia_rc,
    get_cobertura_energia_mensual,
    get_congelamientos_energia_rc,
    get_rachas_constantes_energia,
    get_supuestos,
    get_validacion_energia_rc_mensual,
)
from dashboard.estilos import configurar_grafico, render_alcance_rc_banner, render_callout, render_header


def render(filtros: dict):
    render_header(
        "Calidad de datos y supuestos",
        "Transparencia metodológica: cobertura de telemetría, detección de fallas SCADA y supuestos adoptados"
    )
    render_alcance_rc_banner()

    df_cal_rc = get_calidad_energia_rc()
    df_cal_fa = get_calidad_energia_fa()
    df_cob_mensual = get_cobertura_energia_mensual()
    df_cong_rc = get_congelamientos_energia_rc()
    df_rachas = get_rachas_constantes_energia()
    df_val_rc = get_validacion_energia_rc_mensual()
    supuestos_lista = get_supuestos()

    # ==========================================================================
    # 1. INDICADORES DE CALIDAD SINTÉTICA
    # ==========================================================================
    st.markdown("### Indicadores de integridad de telemetría sintética")

    # 7 medidores de proceso en RC
    med_proc = ["TRITURADO", "HORNO", "REFINO_1", "REFINO_2", "FILTRO_1", "FILTRO_2", "PTARI"]
    sub_rc = df_cal_rc[df_cal_rc["medidor"].isin(med_proc)]

    tot_horas_proc = int(sub_rc["horas_total"].iloc[0]) if not sub_rc.empty else 0
    pct_medido_prom = float(sub_rc["pct_horas_ok_o_interpoladas"].mean()) if not sub_rc.empty else 0.0
    tot_reinicios = int(df_cal_rc["reinicios"].sum())
    tot_horas_reinicio = int(df_cal_rc["horas_reinicio"].sum())
    n_congelamientos = len(df_cong_rc)
    max_congelamiento_h = int(df_cong_rc["horas"].max()) if not df_cong_rc.empty else 0

    ratio_mediana = float(df_val_rc["ratio_scada_vs_base"].median()) if not df_val_rc.empty else 0.0
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Horas por Medidor</span>
                </div>
                <div class="kpi-value">{tot_horas_proc:,.0f} <span style="font-size:1rem;color:#94a3b8">h</span></div>
                <div class="kpi-sub"><strong>{pct_medido_prom:.1f} %</strong> medidas confiables</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with q2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Reinicios de Contador</span>
                </div>
                <div class="kpi-value" style="color:#f59e0b">{tot_reinicios} <span style="font-size:1rem">eventos</span></div>
                <div class="kpi-sub">{tot_horas_reinicio} horas descartadas (sin inventar)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with q3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Congelamientos SCADA</span>
                </div>
                <div class="kpi-value" style="color:#ef4444">{n_congelamientos} <span style="font-size:1rem">episodios</span></div>
                <div class="kpi-sub">Duración máxima: <strong>{max_congelamiento_h} h</strong></div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with q4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">
                    <span>Referencia sintética</span>
                </div>
                <div class="kpi-value" style="color:#212492">{ratio_mediana:.2f} <span style="font-size:1rem">mediana sintética</span></div>
                <div class="kpi-sub">Razón del conjunto de demostración</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ==========================================================================
    # 2. COMPARACIÓN DE SERIES SINTÉTICAS
    # ==========================================================================
    st.markdown("### Comparación mensual de series sintéticas")
    render_callout(
        """
        > [!IMPORTANT]
        > **¿Cómo interpretar esta comparación?**
        > Ambas series son sintéticas y se incluyen para ilustrar una comparación. La serie de medidores
        > agrega procesos seleccionados; no equivale a la energía total de una instalación,
        > y las diferencias no representan una conciliación real,
        > por lo que no se deben extrapolar a una operación real.
        """
    )

    if not df_val_rc.empty:
        df_v_plot = df_val_rc.sort_values("mes").copy()
        df_v_plot["mes_str"] = df_v_plot["mes"].dt.strftime("%Y-%m")

        fig_val = go.Figure()

        # Barra de base esta demostración vs SCADA
        fig_val.add_trace(go.Bar(
            x=df_v_plot["mes_str"],
            y=df_v_plot["kwh_base_clarios"] / 1000.0,
            name="Base esta demostración (MWh)",
            marker_color="rgba(148, 163, 184, 0.4)",
            marker_line_color="#64748b",
            marker_line_width=1
        ))

        fig_val.add_trace(go.Bar(
            x=df_v_plot["mes_str"],
            y=df_v_plot["kwh_scada_7_procesos"] / 1000.0,
            name="SCADA 7 Procesos (MWh)",
            marker_color="#212492"
        ))

        fig_val = configurar_grafico(fig_val, "Energía Mensual: Base esta demostración vs SCADA 7 Medidores (MWh)", altura=340)
        fig_val.update_yaxes(title_text="Energía (MWh)")
        fig_val.update_layout(barmode="group")
        st.plotly_chart(fig_val, use_container_width=True, theme=None)

        # Gráfico de la razón (ratio)
        fig_ratio = go.Figure()
        fig_ratio.add_trace(go.Scatter(
            x=df_v_plot["mes_str"],
            y=df_v_plot["ratio_scada_vs_base"],
            mode="lines+markers",
            name="Razón SCADA / Base esta demostración",
            line={"color": "#f59e0b", "width": 2.5},
            marker={"size": 6}
        ))
        fig_ratio.add_hline(y=ratio_mediana, line_dash="dash", line_color="#10b981", annotation_text=f"Mediana sintética: {ratio_mediana:.2f}")
        fig_ratio = configurar_grafico(fig_ratio, "Evolución de la Razón Mensual (SCADA / Base esta demostración)", altura=300)
        fig_ratio.update_yaxes(title_text="Razón (fracción)")
        st.plotly_chart(fig_ratio, use_container_width=True, theme=None)

    st.markdown("---")

    # ==========================================================================
    # 3. DETALLE DE CALIDAD POR MEDIDOR Y CONGELAMIENTOS
    # ==========================================================================
    col_t1, col_t2 = st.columns([1, 1])

    with col_t1:
        st.markdown("#### Calidad por Medidor de Proceso (RC)")
        df_show_cal = df_cal_rc.copy()
        df_show_cal["% Medido"] = df_show_cal["pct_horas_ok_o_interpoladas"].apply(lambda v: f"{v:.1f}%")
        df_show_cal["Reinicios"] = df_show_cal["reinicios"]
        df_show_cal["Horas Descartadas"] = df_show_cal["horas_reinicio"]

        st.dataframe(
            df_show_cal[["medidor", "horas_total", "% Medido", "Reinicios", "Horas Descartadas"]],
            hide_index=True,
            use_container_width=True
        )
        st.caption("Los valores corresponden exclusivamente a datos sintéticos incluidos para la demostración.")

    with col_t2:
        st.markdown("#### Congelamientos detectados en la serie sintética")
        df_cong_show = df_cong_rc.copy()
        df_cong_show["Inicio"] = df_cong_show["inicio"].dt.strftime("%Y-%m-%d %H:%M")
        df_cong_show["Fin"] = df_cong_show["fin"].dt.strftime("%Y-%m-%d %H:%M")
        df_cong_show["Duración"] = df_cong_show["horas"].apply(lambda v: f"{v:,.0f} h")
        df_cong_show["Energía Repartida"] = df_cong_show["consumo_acumulado_kwh"].apply(lambda v: f"{v:,.0f} kWh")

        st.dataframe(
            df_cong_show[["Inicio", "Fin", "Duración", "Energía Repartida"]],
            hide_index=True,
            use_container_width=True
        )
        st.caption("El consumo entre antes y después se repartió uniformemente (`estimado`) para no perder totales mensuales.")

    st.markdown("---")

    # ==========================================================================
    # 4. TABLA DE SUPUESTOS METODOLÓGICOS (10 SUPUESTOS DE CONFIG.YAML)
    # ==========================================================================
    st.markdown("### Los 10 Supuestos en Uso (Catálogo `config.yaml`)")
    st.markdown(
        "Toda decisión analítica que no contó con validación textual de esta demostración fue parametrizada formalmente "
        "con su justificación técnica y advertencia obligatoria."
    )

    filas_sup = []
    for s in supuestos_lista:
        val_str = str(s["valor"])
        if len(val_str) > 35:
            val_str = val_str[:32] + "..."
        filas_sup.append({
            "Parámetro": s["nombre"],
            "Valor": val_str,
            "Unidad": s.get("unidad", ""),
            "Descripción": s.get("descripcion", ""),
            "Advertencia Obligatoria": s.get("advertencia", "")
        })

    df_supuestos_tabla = pd.DataFrame(filas_sup)
    st.dataframe(
        df_supuestos_tabla,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Parámetro": st.column_config.TextColumn("Parámetro", width="medium"),
            "Advertencia Obligatoria": st.column_config.TextColumn("Advertencia / Límite de Interpretación", width="large")
        }
    )

    # ==========================================================================
    # 5. RESUMEN DE LIMITACIONES (DOCS/04)
    # ==========================================================================
    st.markdown("###  Resumen de Limitaciones del Proyecto (`docs/04`)")
    st.markdown("Los indicadores, periodos y limitaciones que aparecen en esta página se calculan sobre el conjunto sintético de demostración. No deben interpretarse como auditoría de telemetría real.")

