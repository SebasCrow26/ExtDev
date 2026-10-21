"""resumen.py — Pantalla 3.1: Resumen Ejecutivo de RC.

Tarjetas de KPI totales, semáforo por proceso, consumo real vs esperado,
exceso neto en kWh y COP, e intensidad energética contra metas históricas p25.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.datos import (
    calcular_alertas_exceso_sostenido,
    calcular_costo_kwh,
    calcular_semaforo_proceso,
    get_dataset_modelo,
    get_metas,
    get_resultados_modelo,
    get_tarifa_kwh_mensual,
    obtener_alertas_anomalias_puntuales,
    resolver_tarifa,
)
from dashboard.estilos import (
    configurar_grafico,
    render_alcance_rc_banner,
    render_callout,
    render_header,
)


def _abrir_detalle_proceso(proceso: str):
    """Navega al análisis RC con la planta y el proceso de la tarjeta seleccionados."""
    st.session_state["pagina_dashboard_activa"] = "3.2 Detalle Proceso"
    st.session_state["detalle_planta_sel"] = "RC (Procesos Principales)"
    st.session_state["detalle_proc_sel"] = proceso
    st.session_state["detalle_proceso_exceso"] = proceso


def _sparkline_proceso(df: pd.DataFrame, color: str) -> str:
    """Devuelve una minigráfica SVG del consumo diario del proceso."""
    if df.empty or "kwh" not in df or "fecha_turno" not in df:
        return ""
    serie = df.groupby(df["fecha_turno"].dt.date)["kwh"].sum().tail(14).astype(float)
    if serie.empty:
        return ""
    valores = serie.tolist()
    minimo, maximo = min(valores), max(valores)
    amplitud = max(maximo - minimo, 1.0)
    puntos = " ".join(
        f"{(i / max(len(valores) - 1, 1)) * 200:.1f},{30 - ((v - minimo) / amplitud) * 26:.1f}"
        for i, v in enumerate(valores)
    )
    return (
        '<svg viewBox="0 0 200 34" role="img" aria-label="Tendencia diaria de consumo" '
        'style="display:block;width:100%;height:40px;margin-top:8px">'
        f'<polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def render(filtros: dict):
    render_header(
        "Resumen Ejecutivo de Planta",
        "RC · Monitoreo energético en línea"
    )

    c_inicio, c_fin, c_turnos = st.columns([1, 1, 1.8])
    with c_inicio:
        f_ini = st.date_input(
            "Fecha de inicio",
            value=filtros["fecha_inicio"],
            min_value=pd.Timestamp("2025-10-01").date(),
            max_value=pd.Timestamp("2026-09-30").date(),
            key="resumen_fecha_inicio",
        )
    with c_fin:
        f_fin = st.date_input(
            "Fecha de fin",
            value=filtros["fecha_fin"],
            min_value=pd.Timestamp("2025-10-01").date(),
            max_value=pd.Timestamp("2026-09-30").date(),
            key="resumen_fecha_fin",
        )
    with c_turnos:
        turnos_activos = st.multiselect(
            "Turnos",
            options=[1, 2, 3],
            default=[1, 2, 3],
            format_func=lambda t: {1: "Turno 1 · 22:00–06:00", 2: "Turno 2 · 06:00–14:00", 3: "Turno 3 · 14:00–22:00"}[t],
            key="resumen_turnos",
        )
    if f_ini > f_fin:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        return
    filtros = {**filtros, "fecha_inicio": f_ini, "fecha_fin": f_fin, "turnos": turnos_activos}
    if not turnos_activos:
        st.info("Sin turnos seleccionados: los KPI y el desempeño mostrarán cero datos; la sección de intensidad conserva sus filtros propios.")
    turnos_activos = filtros.get("turnos", [])
    nombres_turnos = {1: "Turno 1 (22:00–06:00)", 2: "Turno 2 (06:00–14:00)", 3: "Turno 3 (14:00–22:00)"}
    turnos_texto = " · ".join(nombres_turnos[t] for t in turnos_activos if t in nombres_turnos) or "Sin turnos"
    periodo_texto = f"{filtros['fecha_inicio']:%d %b %Y} – {filtros['fecha_fin']:%d %b %Y}"
    st.markdown(
        f'<div class="filter-strip"><strong>SELECCIÓN ACTIVA</strong><span>Periodo: <b>{periodo_texto}</b></span>'
        f'<span>Turnos: <b>{turnos_texto}</b></span><span class="filter-count">{len(turnos_activos)} turnos</span></div>',
        unsafe_allow_html=True,
    )

    # Carga de datos base
    df_res_todo = get_resultados_modelo()
    df_dm_todo = get_dataset_modelo()
    df_metas = get_metas()
    df_tarifas = get_tarifa_kwh_mensual()

    # Filtrar solo RC
    df_res_rc = df_res_todo[df_res_todo["planta"] == "RC"].copy()
    df_dm_rc = df_dm_todo[df_dm_todo["planta"] == "RC"].copy()

    # Aplicar filtros globales de fecha y turno
    f_ini, f_fin = filtros["fecha_inicio"], filtros["fecha_fin"]
    df_res = df_res_rc[(df_res_rc["fecha_turno"].dt.date >= f_ini) & (df_res_rc["fecha_turno"].dt.date <= f_fin)]
    df_dm = df_dm_rc[(df_dm_rc["fecha_turno"].dt.date >= f_ini) & (df_dm_rc["fecha_turno"].dt.date <= f_fin)]

    if filtros.get("turnos"):
        df_res = df_res[df_res["turno"].isin(filtros["turnos"])]
        df_dm = df_dm[df_dm["turno"].isin(filtros["turnos"])]
    else:
        df_res = df_res.iloc[0:0].copy()
        df_dm = df_dm.iloc[0:0].copy()

    # Si hay filtro de procesos específicos
    if filtros.get("procesos"):
        df_res = df_res[df_res["proceso_modelo"].isin(filtros["procesos"])]
        df_dm = df_dm[df_dm["proceso_modelo"].isin(filtros["procesos"])]

    if df_res.empty:
        st.warning("No hay registros para los filtros seleccionados.")

    # Tarifa aplicable en el periodo (usamos la fecha final para referencia de mes)
    tarifa_val, es_fallback, nota_tarifa = resolver_tarifa(
        pd.Timestamp(f_fin),
        df_tarifas,
        filtros.get("tarifa_override")
    )

    # ==========================================================================
    # TOTALES DE RC (SECCIÓN SUPERIOR)
    # ==========================================================================
    tot_real_kwh = float(df_res["kwh_real"].sum())
    tot_esp_kwh = float(df_res["kwh_esperado"].sum())
    tot_exceso_kwh = tot_real_kwh - tot_esp_kwh
    tot_exceso_pct = 100.0 * tot_exceso_kwh / tot_esp_kwh if tot_esp_kwh > 0 else 0.0

    tot_real_cop = tot_real_kwh * tarifa_val
    tot_esp_cop = tot_esp_kwh * tarifa_val
    tot_exceso_cop = tot_exceso_kwh * tarifa_val

    # Alertas en el periodo
    al_sost = calcular_alertas_exceso_sostenido(
        df_res,
        min_turnos=filtros.get("min_turnos_alerta", 3),
        pct_umbral=filtros.get("pct_umbral_alerta", 10.0),
        min_costo_cop=filtros.get("min_costo_alerta", 100000.0),
        filtro_confianza="todas"
    )
    al_punt = obtener_alertas_anomalias_puntuales(df_res, filtro_confianza="todas")
    n_alertas_tot = len(al_sost) + len(al_punt)

    if es_fallback:
        st.caption(f"{nota_tarifa}")

    color_delta = "#cf4936" if tot_exceso_kwh > 0 else "#4f8b70"
    signo = "+" if tot_exceso_kwh > 0 else ""
    st.markdown(
        f"""
        <div class="kpi-overview">
            <div class="kpi-overview-item">
                <div class="kpi-overview-label">Consumo real</div>
                <div class="kpi-overview-value">{tot_real_kwh:,.0f} kWh</div>
                <div class="kpi-overview-sub">${tot_real_cop / 1_000_000:,.1f} M COP</div>
            </div>
            <div class="kpi-overview-item">
                <div class="kpi-overview-label">Esperado</div>
                <div class="kpi-overview-value">{tot_esp_kwh:,.0f} kWh</div>
                <div class="kpi-overview-sub">${tot_esp_cop / 1_000_000:,.1f} M COP según producción</div>
            </div>
            <div class="kpi-overview-item">
                <div class="kpi-overview-label">Exceso neto</div>
                <div class="kpi-overview-value" style="color:{color_delta}">{signo}{tot_exceso_kwh:,.0f} kWh</div>
                <div class="kpi-overview-sub">{signo}{tot_exceso_pct:.1f}% · {signo}${tot_exceso_cop / 1_000_000:,.1f} M COP</div>
            </div>
            <div class="kpi-overview-item">
                <div class="kpi-overview-label">Alertas del periodo</div>
                <div class="kpi-overview-value">{n_alertas_tot}</div>
                <div class="kpi-overview-sub">{len(al_sost)} de exceso sostenido</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    render_alcance_rc_banner()

    st.markdown("---")

    # ==========================================================================
    # TARJETAS DE PROCESO Y SEMÁFORO
    # ==========================================================================
    st.markdown("### Desempeño energético por proceso")
    st.caption("Calculado sobre la suma total del periodo. Procesos con confianza **baja** se marcan como *indicativos*.")

    verde_hasta = filtros.get("semaforo_verde", 5.0)
    amarillo_hasta = filtros.get("semaforo_amarillo", 10.0)
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;gap:.55rem 1.2rem;align-items:center;"
        f"margin:.25rem 0 1rem;font-size:.82rem;color:#aab4d0;'>"
        f"<span><b style='color:#55e0bd'>● Verde:</b> exceso neto ≤ {verde_hasta:g}%</span>"
        f"<span><b style='color:#ffd36f'>● Amarillo:</b> exceso neto &gt; {verde_hasta:g}% y ≤ {amarillo_hasta:g}%</span>"
        f"<span><b style='color:#ff6688'>● Rojo:</b> exceso neto &gt; {amarillo_hasta:g}% o alerta de severidad alta</span>"
        f"<span><b style='color:#aeb9d1'>● Gris:</b> menos de 75% de turnos válidos</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    procesos_rc = ["triturado", "horno", "refinacion", "filtros", "ptari"]
    if filtros.get("procesos"):
        procesos_rc = [p for p in procesos_rc if p in filtros["procesos"]]

    cols = st.columns(len(procesos_rc))
    nombres_proceso = {
        "triturado": "Triturado",
        "horno": "Horno",
        "refinacion": "Refinación",
        "filtros": "Filtros",
        "ptari": "PTARI",
    }

    for idx, proc in enumerate(procesos_rc):
        d_p = df_res[df_res["proceso_modelo"] == proc]
        dm_p = df_dm[df_dm["proceso_modelo"] == proc]

        sem = calcular_semaforo_proceso(
            d_p,
            dm_p,
            verde_hasta_pct=filtros.get("semaforo_verde", 5.0),
            amarillo_hasta_pct=filtros.get("semaforo_amarillo", 10.0)
        )

        # Costo exceso proceso
        costo_p = sem["exceso_kwh"] * tarifa_val
        signo_p = "+" if sem["exceso_kwh"] > 0 else ""

        # Alertas específicas del proceso
        al_proc = 0
        if not al_sost.empty:
            al_proc += len(al_sost[al_sost["proceso"] == proc])
        if not al_punt.empty:
            al_proc += len(al_punt[al_punt["proceso"] == proc])

        # Clases de badge
        badge_cls = f"badge-{sem['color']}"
        conf_cls = f"conf-{sem['confianza']}"
        color_semaforo = {
            "rojo": "#ff6688",
            "amarillo": "#ffd36f",
            "verde": "#55e0bd",
            "gris": "#aeb9d1",
        }.get(sem["color"], "#aeb9d1")
        etiqueta_indicativo = '<span style="color:#ffd36f; font-size:0.68rem; font-weight:600"> · INDICATIVO</span>' if sem["indicativo"] else ""
        escala_kwh = max(float(sem["kwh_real"]), float(sem["kwh_esperado"]), 1.0)
        ancho_real = min(100.0, float(sem["kwh_real"]) / escala_kwh * 100)
        ancho_esperado = min(100.0, float(sem["kwh_esperado"]) / escala_kwh * 100)
        sparkline = _sparkline_proceso(dm_p, color_semaforo)

        with cols[idx]:
            st.markdown(
                f"""
                <div class="proceso-card">
                    <div class="proceso-header">
                        <span class="proceso-nombre">{nombres_proceso[proc]}</span>
                        <span class="badge-semaforo {badge_cls}">● {sem['color'].upper()}</span>
                    </div>
                    <div style="margin-bottom:0.75rem;">
                        <span class="badge-confianza {conf_cls}">Confianza {sem['confianza']}</span>{etiqueta_indicativo}
                    </div>
                    <div style="font-size:0.78rem;color:#aab4d0;display:grid;grid-template-columns:48px 1fr 58px;gap:7px;align-items:center;margin:7px 0;">
                        <span>Real</span><span style="height:6px;background:#242b46;border-radius:5px;overflow:hidden"><i style="display:block;width:{ancho_real:.1f}%;height:100%;background:#8d68ff;border-radius:5px"></i></span><b style="color:#f3f5ff;text-align:right">{sem['kwh_real']:,.0f}</b>
                        <span>Esperado</span><span style="height:6px;background:#242b46;border-radius:5px;overflow:hidden"><i style="display:block;width:{ancho_esperado:.1f}%;height:100%;background:#96a3c0;border-radius:5px"></i></span><b style="color:#f3f5ff;text-align:right">{sem['kwh_esperado']:,.0f}</b>
                    </div>
                    <div style="font-size:0.85rem; color:#596273; margin-top:0.6rem; margin-bottom:0.25rem;">Exceso neto</div>
                    <div style="font-weight:700; font-size:1.15rem; color:{color_semaforo};">
                        {signo_p}{sem['exceso_kwh']:,.0f} kWh
                    </div>
                    <div style="font-size:0.82rem; color:#596273; margin-top:0.2rem;">
                        {signo_p}${costo_p:,.0f} COP
                    </div>
                    {sparkline}
                    <div style="margin-top:0.75rem; padding-top:0.5rem; border-top:1px dashed #deded9; font-size:0.8rem; color:#596273; display:flex; justify-content:space-between;">
                        <span>Alertas: <strong class="card-meta-value">{al_proc}</strong></span>
                        <span>Válidos: <strong class="card-meta-value">{sem['turnos_validos']*100:.0f}%</strong></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.button(
                "Abrir detalle",
                key=f"abrir_detalle_{proc}",
                use_container_width=True,
                on_click=_abrir_detalle_proceso,
                args=(proc,),
            )

    st.markdown("---")

    # ==========================================================================
    # INTENSIDAD ENERGÉTICA VS META HISTÓRICA (P25)
    # ==========================================================================
    st.markdown("### Intensidad Energética vs Meta Histórica (p25)")
    render_callout(
        """
        > [!NOTE]
        > **Cálculo exacto:** kWh total dividido entre producción total del periodo (no promedio de cocientes).
        > En RC se expresa en **kWh por tonelada** (×1,000). Por la producción por lotes, la agregación semanal es la más representativa.
        > Las metas p25 se cargan de la tabla sintética `metas.csv` y son referencias ilustrativas de esta demo.
        """
    )

    c_int_ini, c_int_fin = st.columns(2)
    with c_int_ini:
        f_int_ini = st.date_input(
            "Fecha de inicio · intensidad vs meta",
            value=pd.Timestamp("2025-10-01").date(),
            min_value=pd.Timestamp("2025-10-01").date(),
            max_value=pd.Timestamp("2026-09-30").date(),
            key="resumen_intensidad_fecha_inicio",
        )
    with c_int_fin:
        f_int_fin = st.date_input(
            "Fecha de fin · intensidad vs meta",
            value=pd.Timestamp("2026-09-30").date(),
            min_value=pd.Timestamp("2025-10-01").date(),
            max_value=pd.Timestamp("2026-09-30").date(),
            key="resumen_intensidad_fecha_fin",
        )
    intensidad_rango_valido = f_int_ini <= f_int_fin
    if not intensidad_rango_valido:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
    df_dm_intensidad = df_dm_rc[
        (df_dm_rc["fecha_turno"].dt.date >= f_int_ini)
        & (df_dm_rc["fecha_turno"].dt.date <= f_int_fin)
    ].copy() if intensidad_rango_valido else df_dm_rc.iloc[0:0].copy()
    st.caption(
        "Este periodo es independiente de los filtros superiores y considera los tres turnos, "
        "igual que la referencia p25 agregada por proceso."
    )

    # Metas en diccionario (kWh/kg a kWh/t -> ×1000)
    metas_rc = df_metas[df_metas["planta"].astype(str).str.upper() == "RC"].copy()
    metas_rc["meta_kwh_t"] = pd.to_numeric(metas_rc["meta_kwh_por_unidad"], errors="coerce") * 1000.0
    metas_dict = metas_rc.set_index("proceso_modelo")["meta_kwh_t"].to_dict()

    filas_intensidad = []
    for proc in procesos_rc:
        # Sumas del periodo propio de intensidad, considerando los tres turnos.
        dm_p = df_dm_intensidad[df_dm_intensidad["proceso_modelo"] == proc]
        kwh_tot = float(dm_p["kwh"].sum())
        prod_tot = float(dm_p["produccion"].sum())

        if prod_tot > 0:
            intensidad_t = (kwh_tot / prod_tot) * 1000.0  # kWh / tonelada
        else:
            intensidad_t = 0.0

        meta_t = metas_dict.get(proc, 0.0)
        cumplimiento = (intensidad_t / meta_t * 100.0) if meta_t > 0 else 0.0
        desv_pct = ((intensidad_t - meta_t) / meta_t * 100.0) if meta_t > 0 else 0.0

        filas_intensidad.append({
            "Proceso": proc.capitalize(),
            "Consumo (kWh)": f"{kwh_tot:,.0f}",
            "Producción (t)": f"{prod_tot / 1000.0:,.1f}",
            "Intensidad (kWh/t)": round(intensidad_t, 2),
            "Meta p25 (kWh/t)": meta_t,
            "Desviación vs Meta": f"{'+' if desv_pct > 0 else ''}{desv_pct:.1f}%",
            "Cumple": "Sí" if intensidad_t <= meta_t and intensidad_t > 0 else (" No" if intensidad_t > 0 else "Sin Prod.")
        })

    df_int_show = pd.DataFrame(filas_intensidad)

    c_tbl, c_fig = st.columns([1, 1])

    with c_tbl:
        st.dataframe(
            df_int_show,
            hide_index=True,
            use_container_width=True
        )
        st.caption("Filtros y PTARI asocian la producción de refinación (supuesto metodológico). No sumar producción entre procesos.")

    with c_fig:
        # Gráfico comparativo de barras de intensidad vs meta
        fig_int = go.Figure()

        nombres = [r["Proceso"] for r in filas_intensidad]
        valores = [r["Intensidad (kWh/t)"] for r in filas_intensidad]
        metas = [r["Meta p25 (kWh/t)"] for r in filas_intensidad]

        fig_int.add_trace(go.Bar(
            name="Intensidad Real (kWh/t)",
            x=nombres,
            y=valores,
            marker_color="#212492",
            text=[f"{v:.1f}" for v in valores],
            textposition="auto"
        ))

        fig_int.add_trace(go.Bar(
            name="Meta p25 (kWh/t)",
            x=nombres,
            y=metas,
            marker_color="#f5b82e",
            text=[f"{m:.1f}" for m in metas],
            textposition="auto"
        ))

        fig_int = configurar_grafico(fig_int, "Comparativo Intensidad vs Meta p25 (kWh/t)", altura=320)
        fig_int.update_layout(
            barmode="group",
            legend={"orientation": "h", "yanchor": "top", "y": -0.2, "xanchor": "center", "x": 0.5},
            margin={"l": 45, "r": 25, "t": 60, "b": 85},
        )
        st.plotly_chart(fig_int, use_container_width=True, theme=None)

    # ==========================================================================
    # SERIE SEMANAL DE INTENSIDAD
    # ==========================================================================
    if not df_dm_rc.empty:
        st.markdown("#### Evolución semanal de la intensidad")
        semanas_disponibles = sorted((
            df_dm_rc["fecha_turno"]
            - pd.to_timedelta(df_dm_rc["fecha_turno"].dt.weekday, unit="D")
        ).dt.normalize().drop_duplicates().tolist(), reverse=True)
        proceso_sem, desde_sem_col, hasta_sem_col = st.columns([1.25, 1, 1])
        with proceso_sem:
            proc_sel_int = st.selectbox(
                "Proceso:", options=procesos_rc, index=0, key="sel_proc_int_semana"
            )
        with desde_sem_col:
            desde_semana = st.selectbox(
                "Desde semana (lunes):", options=semanas_disponibles,
                index=min(12, len(semanas_disponibles) - 1),
                format_func=lambda fecha: fecha.strftime("%d %b %Y"),
                key="resumen_intensidad_desde_semana_v2",
            )
        with hasta_sem_col:
            hasta_semana = st.selectbox(
                "Hasta semana (lunes):", options=semanas_disponibles,
                index=0,
                format_func=lambda fecha: fecha.strftime("%d %b %Y"),
                key="resumen_intensidad_hasta_semana_v2",
            )

        st.caption(
            "La línea p25 es una referencia agregada del proceso; no representa una meta independiente para cada turno."
        )
        if desde_semana > hasta_semana:
            st.warning("La semana inicial debe ser anterior o igual a la semana final.")
        else:
            dm_semana = df_dm_rc[
                (df_dm_rc["proceso_modelo"] == proc_sel_int)
                & (df_dm_rc["fecha_turno"] >= pd.Timestamp(desde_semana))
                & (df_dm_rc["fecha_turno"] < pd.Timestamp(hasta_semana) + pd.Timedelta(days=7))
            ].copy()
            dm_semana["semana_inicio"] = (
                dm_semana["fecha_turno"]
                - pd.to_timedelta(dm_semana["fecha_turno"].dt.weekday, unit="D")
            ).dt.normalize()
            meta_val = metas_dict.get(proc_sel_int, 0)

            def crear_grafica_semanal(datos, titulo, nombre_serie, color):
                serie = datos[datos["produccion"] > 0].copy()
                if serie.empty:
                    return None
                serie["intensidad_kwh_t"] = (serie["kwh"] / serie["produccion"]) * 1000.0
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=serie["semana_inicio"], y=serie["intensidad_kwh_t"],
                    mode="lines+markers", name=nombre_serie,
                    line={"color": color, "width": 2.5}, marker={"size": 6},
                ))
                fig.add_hline(
                    y=meta_val, line_dash="dash", line_color="#10b981",
                    annotation_text=f"Meta p25: {meta_val:g}", annotation_position="bottom right",
                )
                fig = configurar_grafico(fig, titulo, altura=300)
                fig.update_yaxes(title_text="kWh/t")
                fig.update_xaxes(tickformat="%d %b %y")
                return fig

            general = (
                dm_semana.groupby("semana_inicio", as_index=False)
                .agg(kwh=("kwh", "sum"), produccion=("produccion", "sum"))
                .sort_values("semana_inicio")
            )
            fig_general = crear_grafica_semanal(
                general, f"Intensidad semanal general · {proc_sel_int.capitalize()}",
                "Todos los turnos", "#35e6e6",
            )
            if fig_general is not None:
                st.plotly_chart(fig_general, use_container_width=True, theme=None)

            columnas_turnos = st.columns(3)
            colores_turnos = {1: "#35e6e6", 2: "#a78bfa", 3: "#fb7185"}
            for turno, columna in zip((1, 2, 3), columnas_turnos):
                dm_turno = dm_semana[dm_semana["turno"] == turno]
                semanal_turno = (
                    dm_turno.groupby("semana_inicio", as_index=False)
                    .agg(kwh=("kwh", "sum"), produccion=("produccion", "sum"))
                    .sort_values("semana_inicio")
                )
                fig_turno = crear_grafica_semanal(
                    semanal_turno,
                    f"Intensidad semanal · Turno {turno}",
                    f"Turno {turno}", colores_turnos[turno],
                )
                with columna:
                    if fig_turno is None:
                        st.info(f"Sin producción suficiente para T{turno} en estas semanas.")
                    else:
                        st.plotly_chart(fig_turno, use_container_width=True, theme=None)
