"""Pantalla mensual por planta: consumo, producción equivalente y presupuesto."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dashboard.datos import (
    get_base_mensual_plantas,
    get_metas_clarios,
    get_pronostico_mensual_plantas,
)
from dashboard.estilos import configurar_grafico, render_header


PALETA_PLANTAS = {
    "Ensamble": "#36d8dc",
    "OREC": "#8d68ff",
    "F&A": "#1bc6a0",
    "RC": "#ff6688",
}


def _variacion(actual: float, anterior: float, menor_es_mejor: bool = True) -> tuple[str, str]:
    if pd.isna(anterior) or anterior == 0 or pd.isna(actual):
        return "Sin comparación", "neutral"
    cambio = (actual / anterior - 1) * 100
    if cambio == 0:
        estado = "neutral"
    else:
        es_favorable = (cambio < 0) if menor_es_mejor else (cambio > 0)
        estado = "down" if es_favorable else "up"
    return f"{cambio:+.1f}% vs. mes anterior", estado


def _texto_mes(fecha: pd.Timestamp) -> str:
    meses_es = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{meses_es[fecha.month - 1].capitalize()} {fecha.year}"


def _sincronizar_mes_con_anio(anio_key, mes_key, meses_por_anio, extremo):
    """Conserva el mes si existe en el año elegido; si no, elige un extremo disponible."""
    anio = st.session_state[anio_key]
    meses = sorted(meses_por_anio[anio])
    if st.session_state.get(mes_key) not in meses:
        st.session_state[mes_key] = meses[0] if extremo == "inicio" else meses[-1]


def render(filtros: dict):
    render_header("Plantas", "Consumo eléctrico · Producción equivalente · Presupuesto")

    df_base = get_base_mensual_plantas().copy()
    df_metas = get_metas_clarios().copy()
    df_pron = get_pronostico_mensual_plantas().copy()
    if df_base.empty:
        st.info("No hay datos mensuales disponibles para las plantas.")
        return

    df_base["mes"] = pd.to_datetime(df_base["mes"])
    meses_disponibles = sorted(df_base["mes"].dropna().unique())
    fechas_mes = [pd.Timestamp(m).replace(day=1) for m in meses_disponibles]
    meses_por_anio = {}
    for fecha_mes in fechas_mes:
        meses_por_anio.setdefault(int(fecha_mes.year), set()).add(int(fecha_mes.month))
    anios_disponibles = sorted(meses_por_anio, reverse=True)
    indice_inicio_default = min(11, len(fechas_mes) - 1)
    plantas = sorted(df_base["planta"].dropna().unique().tolist())
    opciones_plantas = ["Todas las plantas", *plantas]
    if st.session_state.get("plantas_selector") not in opciones_plantas:
        st.session_state["plantas_selector"] = "Todas las plantas"
    # Se lee antes de calcular los KPI, aunque el control se dibuje junto al presupuesto más abajo.
    planta_sel = st.session_state["plantas_selector"]

    meses_nombres = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    def selector_mes(etiqueta, state_key, fecha_default, extremo):
        anio_key = f"{state_key}_anio_v3"
        mes_key = f"{state_key}_mes_v3"
        if st.session_state.get(anio_key) not in anios_disponibles:
            st.session_state[anio_key] = int(fecha_default.year)
        if st.session_state.get(mes_key) not in meses_por_anio[st.session_state[anio_key]]:
            disponibles = sorted(meses_por_anio[st.session_state[anio_key]])
            st.session_state[mes_key] = (
                fecha_default.month if fecha_default.month in disponibles
                else (disponibles[0] if extremo == "inicio" else disponibles[-1])
            )

        st.markdown(f"**{etiqueta}**")
        col_anio, col_mes = st.columns([1, 1.35])
        with col_anio:
            st.selectbox(
                "Año",
                options=anios_disponibles,
                key=anio_key,
                on_change=_sincronizar_mes_con_anio,
                args=(anio_key, mes_key, meses_por_anio, extremo),
            )
        with col_mes:
            meses_disponibles_anio = sorted(meses_por_anio[st.session_state[anio_key]])
            st.selectbox(
                "Mes",
                options=meses_disponibles_anio,
                format_func=lambda mes: meses_nombres[mes - 1],
                key=mes_key,
            )
        return pd.Timestamp(
            year=st.session_state[anio_key], month=st.session_state[mes_key], day=1
        )

    mes_inicio_default = fechas_mes[-1 - indice_inicio_default]
    mes_fin_default = fechas_mes[-1]
    c_desde, c_hasta = st.columns(2)
    with c_desde:
        mes_inicio = selector_mes("Desde", "plantas_rango_inicio", mes_inicio_default, "inicio")
    with c_hasta:
        mes_fin = selector_mes("Hasta", "plantas_rango_fin", mes_fin_default, "fin")

    if mes_inicio > mes_fin:
        mes_inicio, mes_fin = mes_fin, mes_inicio
    fin_exclusivo = mes_fin + pd.offsets.MonthBegin(1)
    df_periodo = df_base[(df_base["mes"] >= mes_inicio) & (df_base["mes"] < fin_exclusivo)].copy()

    if planta_sel == "Todas las plantas":
        df_metrica = (
            df_periodo.groupby("mes", as_index=False)
            .agg(
                kwh=("kwh", lambda s: s.sum(min_count=1)),
                produccion_equivalente=("produccion_equivalente", lambda s: s.sum(min_count=1)),
                costo_total_cop=("costo_total_cop", lambda s: s.sum(min_count=1)),
            )
            .sort_values("mes")
        )
        df_metrica["kwh_por_eq"] = df_metrica["kwh"] / df_metrica["produccion_equivalente"].where(
            df_metrica["produccion_equivalente"] != 0
        )
        df_p = df_periodo.copy()
        subtitulo_kpi = "Consolidado de las plantas con dato mensual"
    else:
        df_p = df_periodo[df_periodo["planta"] == planta_sel].sort_values("mes").copy()
        df_metrica = df_p.sort_values("mes").copy()
        subtitulo_kpi = f"Planta {planta_sel} · base mensual"

    if planta_sel == "Todas las plantas":
        df_comparacion = (
            df_base.groupby("mes", as_index=False)
            .agg(
                kwh=("kwh", lambda s: s.sum(min_count=1)),
                produccion_equivalente=("produccion_equivalente", lambda s: s.sum(min_count=1)),
                costo_total_cop=("costo_total_cop", lambda s: s.sum(min_count=1)),
            )
            .sort_values("mes")
        )
        df_comparacion["kwh_por_eq"] = df_comparacion["kwh"] / df_comparacion["produccion_equivalente"].where(
            df_comparacion["produccion_equivalente"] != 0
        )
    else:
        df_comparacion = df_base[df_base["planta"] == planta_sel].sort_values("mes").copy()

    if df_metrica.empty:
        st.info("No hay registros para la planta y el intervalo mensual seleccionados.")
        return

    # Las métricas siempre corresponden al límite superior seleccionado en "Hasta".
    mes_actual = mes_fin
    filas_mes_actual = df_metrica[df_metrica["mes"] == mes_actual]
    actual = filas_mes_actual.iloc[-1] if not filas_mes_actual.empty else pd.Series(dtype=float)
    if filas_mes_actual.empty:
        st.info(f"No hay datos de {planta_sel} para {_texto_mes(mes_actual)}.")
    mes_anterior = mes_actual - pd.offsets.MonthBegin(1)
    anteriores = df_comparacion[df_comparacion["mes"] == mes_anterior]
    anterior = anteriores.iloc[-1] if not anteriores.empty else None
    valor_anterior = lambda col: float(anterior[col]) if anterior is not None and pd.notna(anterior[col]) else float("nan")

    def _valor_texto(valor: float, decimales: int = 0) -> str:
        return "Sin dato" if pd.isna(valor) else f"{valor:,.{decimales}f}"

    consumo_actual = actual.get("kwh", float("nan"))
    produccion_actual = actual.get("produccion_equivalente", float("nan"))
    indicador_actual = actual.get("kwh_por_eq", float("nan"))
    consumo = float(consumo_actual) if pd.notna(consumo_actual) else float("nan")
    produccion = float(produccion_actual) if pd.notna(produccion_actual) else float("nan")
    indicador = float(indicador_actual) if pd.notna(indicador_actual) else float("nan")
    consumo_delta, consumo_tendencia = _variacion(consumo, valor_anterior("kwh"))
    produccion_delta, produccion_tendencia = _variacion(
        produccion, valor_anterior("produccion_equivalente"), menor_es_mejor=False
    )
    indicador_delta, indicador_tendencia = _variacion(indicador, valor_anterior("kwh_por_eq"))

    st.markdown(f"#### Métricas clave del periodo · {_texto_mes(mes_actual)}")
    st.caption(subtitulo_kpi)
    if anterior is None:
        st.caption(f"No hay datos del mes calendario anterior ({_texto_mes(mes_anterior)}) para comparar.")
    elif planta_sel == "Todas las plantas":
        n_actual = int(df_base.loc[df_base["mes"] == mes_actual, "planta"].nunique())
        n_anterior = int(df_base.loc[df_base["mes"] == mes_anterior, "planta"].nunique())
        if n_actual != n_anterior:
            st.caption(
                f"Cobertura del consolidado: {n_actual} plantas en {_texto_mes(mes_actual)} y "
                f"{n_anterior} en {_texto_mes(mes_anterior)}; el cambio puede reflejar esta diferencia."
            )
    st.markdown(
        f"""
        <div class="plant-kpi-grid">
            <div class="plant-kpi-card">
                <small>Consumo total eléctrico</small>
                <strong>{_valor_texto(consumo)} <i>kWh</i></strong>
                <span class="plant-delta {consumo_tendencia}">{consumo_delta}</span>
                <p>{_texto_mes(mes_anterior)}: {_valor_texto(valor_anterior('kwh'))} kWh</p>
            </div>
            <div class="plant-kpi-card">
                <small>Producción equivalente</small>
                <strong>{_valor_texto(produccion)} <i>eq</i></strong>
                <span class="plant-delta {produccion_tendencia}">{produccion_delta}</span>
                <p>{_texto_mes(mes_anterior)}: {_valor_texto(valor_anterior('produccion_equivalente'))} eq</p>
            </div>
            <div class="plant-kpi-card">
                <small>Indicador · kWh / prod. eq.</small>
                <strong>{_valor_texto(indicador, 2)} <i>kWh/eq</i></strong>
                <span class="plant-delta {indicador_tendencia}">{indicador_delta}</span>
                <p>{_texto_mes(mes_anterior)}: {_valor_texto(valor_anterior('kwh_por_eq'), 2)} kWh/eq</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Desempeño vs. meta sintética")
    st.caption(f"Comparación mensual de {_texto_mes(mes_inicio)} a {_texto_mes(mes_fin)} · Consumo y producción equivalente")
    if planta_sel == "Todas las plantas":
        st.markdown("#### Tendencia mensual · todas las plantas")
    c_meta, c_hist = st.columns([0.82, 2.18])

    with c_meta:
        st.selectbox(
            "Planta",
            options=opciones_plantas,
            key="plantas_selector",
        )
        if planta_sel == "Todas las plantas":
            st.markdown(
                """
                <div class="plant-budget-card">
                    <small>Alcance seleccionado</small>
                    <strong>Todas las plantas</strong>
                    <p>El indicador consolidado es el consumo total dividido por la producción equivalente total.</p>
                    <p>No se aplica una meta única: los metas sintéticas son específicos para cada planta.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            metas_planta = df_metas[df_metas["planta"] == planta_sel].copy() if not df_metas.empty else pd.DataFrame()
            meta_val = None
            if not metas_planta.empty:
                metas_planta["vigente_desde"] = pd.to_datetime(metas_planta["vigente_desde"], errors="coerce")
                if "vigente_hasta" in metas_planta:
                    metas_planta["vigente_hasta"] = pd.to_datetime(metas_planta["vigente_hasta"], errors="coerce")
                    metas_planta = metas_planta[
                        (metas_planta["vigente_desde"] <= mes_actual)
                        & (metas_planta["vigente_hasta"].isna() | (metas_planta["vigente_hasta"] >= mes_actual))
                    ]
                else:
                    metas_planta = metas_planta[metas_planta["vigente_desde"] <= mes_actual]
                metas_planta = metas_planta.sort_values("vigente_desde")
                if not metas_planta.empty:
                    meta_val = float(metas_planta.iloc[-1]["kwh_por_eq_meta"])
            if meta_val is None and "kwh_por_eq_presupuesto" in df_p:
                disponibles = df_p.dropna(subset=["kwh_por_eq_presupuesto"])
                if not disponibles.empty:
                    meta_val = float(disponibles.iloc[-1]["kwh_por_eq_presupuesto"])

            if meta_val is None:
                presupuesto_html = "<strong>Sin presupuesto registrado</strong><p>No hay una meta corporativa disponible para esta planta.</p>"
            else:
                desviacion = (indicador / meta_val - 1) * 100 if pd.notna(indicador) and meta_val else float("nan")
                clase_estado = "good" if pd.notna(desviacion) and desviacion <= 0 else "bad"
                presupuesto_html = (
                    f"<strong>{meta_val:.3f} <i>kWh/eq</i></strong>"
                    f"<p>Indicador del periodo: {indicador:.3f} kWh/eq</p>"
                    f"<span class='plant-budget-status {clase_estado}'>"
                    f"{desviacion:+.1f}% vs. presupuesto</span>"
                )
            st.markdown(
                f"""
                <div class="plant-budget-card">
                    <small>Planta seleccionada</small>
                    <strong>{planta_sel}</strong>
                    <hr><small>Meta sintética</small>
                    {presupuesto_html}
                    <p>Meta ilustrativa del periodo para el periodo seleccionado.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with c_hist:
        if planta_sel == "Todas las plantas":
            fig_consumo = go.Figure()
            fig_produccion = go.Figure()
            for nombre in plantas:
                d = df_p[df_p["planta"] == nombre].sort_values("mes")
                fig_consumo.add_trace(
                    go.Scatter(x=d["mes"], y=d["kwh"], mode="lines+markers", name=nombre,
                               line={"color": PALETA_PLANTAS.get(nombre, "#36d8dc"), "width": 2}),
                )
                fig_produccion.add_trace(
                    go.Scatter(x=d["mes"], y=d["produccion_equivalente"], mode="lines+markers", name=nombre,
                               line={"color": PALETA_PLANTAS.get(nombre, "#36d8dc"), "width": 2, "dash": "dot"}),
                )

            opciones_leyenda = {
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 1.08,
                "yanchor": "bottom",
                "font": {"size": 10, "color": "#cbd4eb"},
                "bgcolor": "rgba(0,0,0,0)",
            }
            st.markdown("##### Consumo eléctrico por planta (kWh)")
            fig_consumo = configurar_grafico(fig_consumo, altura=310)
            fig_consumo.update_layout(margin={"l": 55, "r": 25, "t": 60, "b": 45}, legend=opciones_leyenda)
            fig_consumo.update_yaxes(title_text="kWh")
            fig_consumo.update_xaxes(range=[mes_inicio, fin_exclusivo])
            st.plotly_chart(fig_consumo, use_container_width=True, theme=None)

            st.markdown("##### Producción equivalente por planta")
            fig_produccion = configurar_grafico(fig_produccion, altura=310)
            fig_produccion.update_layout(
                margin={"l": 55, "r": 25, "t": 60, "b": 45},
                legend=opciones_leyenda,
            )
            fig_produccion.update_yaxes(title_text="Producción equivalente")
            fig_produccion.update_xaxes(range=[mes_inicio, fin_exclusivo])
            st.plotly_chart(fig_produccion, use_container_width=True, theme=None)
        else:
            fig_hist = make_subplots(specs=[[{"secondary_y": True}]])
            fig_hist.add_trace(
                go.Scatter(
                    x=df_p["mes"], y=df_p["produccion_equivalente"], name="Producción equivalente",
                    mode="lines+markers", line={"color": "#1bc6a0", "width": 2.5}, marker={"size": 4},
                ),
                secondary_y=True,
            )
            fig_hist.add_trace(
                go.Scatter(
                    x=df_p["mes"], y=df_p["kwh"], mode="lines+markers", name="Consumo eléctrico (kWh)",
                    line={"color": "#8d68ff", "width": 2.5}, marker={"size": 4},
                ),
                secondary_y=False,
            )
            fig_hist = configurar_grafico(
                fig_hist, f"Desempeño vs. meta sintética · {planta_sel}", altura=390
            )
            fig_hist.update_yaxes(title_text="Consumo eléctrico (kWh)", secondary_y=False)
            fig_hist.update_yaxes(title_text="Producción equivalente", secondary_y=True, showgrid=False)
            fig_hist.update_xaxes(range=[mes_inicio, fin_exclusivo])
            st.plotly_chart(fig_hist, use_container_width=True, theme=None)

    with st.expander("Análisis del indicador y el efecto del volumen de producción", expanded=False):
        st.markdown(
            "El indicador **kWh por unidad equivalente** se calcula como consumo total dividido por producción "
            "equivalente total del mes. Cuando baja mucho la producción, el consumo base de la planta puede hacer "
            "que el indicador aumente aunque el consumo eléctrico total haya disminuido. Por eso debe interpretarse "
            "junto con consumo, producción, calendario operativo y presupuesto."
        )
        if planta_sel == "Todas las plantas":
            df_ind = df_comparacion[
                (df_comparacion["mes"] >= mes_inicio)
                & (df_comparacion["mes"] < fin_exclusivo)
            ].dropna(subset=["kwh_por_eq"]).copy()
            nombre_indicador = "Indicador consolidado mensual"
        elif "kwh_por_eq" in df_p:
            df_ind = df_p.dropna(subset=["kwh_por_eq"]).copy()
            nombre_indicador = "Indicador mensual"
        else:
            df_ind = pd.DataFrame()
            nombre_indicador = "Indicador mensual"
        if not df_ind.empty:
            fig_ind = go.Figure()
            fig_ind.add_trace(go.Scatter(
                x=df_ind["mes"], y=df_ind["kwh_por_eq"], mode="lines+markers",
                name=nombre_indicador, line={"color": "#36d8dc", "width": 2.5},
            ))
            if planta_sel != "Todas las plantas" and meta_val is not None:
                fig_ind.add_hline(y=meta_val, line_dash="dash", line_color="#ff6688",
                                  annotation_text=f"Presupuesto {meta_val:.3f} kWh/eq")
            titulo_indicador = (
                "Indicador consolidado mensual · sin presupuesto común"
                if planta_sel == "Todas las plantas"
                else f"Indicador mensual · {planta_sel}"
            )
            fig_ind = configurar_grafico(fig_ind, titulo_indicador, altura=300)
            fig_ind.update_yaxes(title_text="kWh / equivalente")
            st.plotly_chart(fig_ind, use_container_width=True, theme=None)

    with st.expander("Pronóstico mensual de Ensamble y OREC", expanded=False):
        if df_pron.empty:
            st.info("No hay pronósticos mensuales disponibles.")
        else:
            df_show = df_pron.copy()
            df_show["Mes"] = pd.to_datetime(df_show["mes_pronosticado"]).dt.strftime("%b %Y")
            df_show["Consumo previsto (kWh)"] = df_show["kwh_pronosticado"].round(0)
            df_show["Indicador previsto (kWh/eq)"] = df_show["kwh_por_eq_pronosticado"].round(3)
            df_show["Presupuesto (kWh/eq)"] = df_show["presupuesto_kwh_por_eq"].round(3)
            df_show["Cumple meta"] = df_show["cumple_pronostico"].apply(
                lambda v: "Sí" if str(v).strip().lower() in ("si", "sí", "true", "1") else "No"
            )
            st.dataframe(
                df_show[["planta", "Mes", "Consumo previsto (kWh)", "Indicador previsto (kWh/eq)",
                         "Presupuesto (kWh/eq)", "Cumple meta"]],
                hide_index=True,
                use_container_width=True,
            )
