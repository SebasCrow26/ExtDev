"""alertas.py — Pantalla 3.3: Gestión y Monitoreo de Alertas.

Lista priorizada de eventos por costo de exceso en COP, separación entre alertas
firmes e indicativas (baja confianza), y avisos operativos de calidad de datos.
"""
from __future__ import annotations

import datetime
import html
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.configuracion import texto
from dashboard.datos import (
    calcular_alertas_exceso_sostenido,
    get_anomalias_candidatas_rc,
    get_dataset_modelo,
    get_resultados_modelo,
    get_tarifa_kwh_mensual,
    obtener_alertas_anomalias_puntuales,
    obtener_alertas_candidatas,
    obtener_avisos_calidad_turnos_incompletos,
)
from dashboard.estilos import configurar_grafico, render_callout, render_header


def render(filtros: dict):
    render_header(
        "Gestión y Monitoreo de Alertas",
        "Alertas operativas · Calidad y desviaciones"
    )
    c_ini, c_fin = st.columns(2)
    with c_ini:
        f_ini = st.date_input(
            "Fecha de inicio", value=filtros["fecha_inicio"],
            min_value=datetime.date(2025, 10, 1), max_value=datetime.date(2026, 9, 30),
            key="alertas_fecha_inicio",
        )
    with c_fin:
        f_fin = st.date_input(
            "Fecha de fin", value=filtros["fecha_fin"],
            min_value=datetime.date(2025, 10, 1), max_value=datetime.date(2026, 9, 30),
            key="alertas_fecha_fin",
        )
    if f_ini > f_fin:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")
        return
    filtros = {**filtros, "fecha_inicio": f_ini, "fecha_fin": f_fin}
    df_res_todo = get_resultados_modelo()
    df_dm_todo = get_dataset_modelo()
    df_cand = get_anomalias_candidatas_rc()
    df_tarifas = get_tarifa_kwh_mensual()

    # Filtrar datos de RC
    df_res = df_res_todo[df_res_todo["planta"] == "RC"].copy()
    df_dm = df_dm_todo[df_dm_todo["planta"] == "RC"].copy()

    # Periodo específico de esta pantalla
    df_res_f = df_res[(df_res["fecha_turno"].dt.date >= f_ini) & (df_res["fecha_turno"].dt.date <= f_fin)].copy()
    df_dm_f = df_dm[(df_dm["fecha_turno"].dt.date >= f_ini) & (df_dm["fecha_turno"].dt.date <= f_fin)].copy()
    df_cand_f = df_cand[(df_cand["fecha_turno"].dt.date >= f_ini) & (df_cand["fecha_turno"].dt.date <= f_fin)].copy()

    # Parámetros editables de alertas
    min_turnos = filtros.get("min_turnos_alerta", 3)
    pct_umbral = filtros.get("pct_umbral_alerta", 10.0)
    min_costo = filtros.get("min_costo_alerta", 100000.0)

    # 1. Alertas firmes (alta y media confianza)
    al_sost_firmes = calcular_alertas_exceso_sostenido(
        df_res_f, min_turnos, pct_umbral, min_costo, filtro_confianza="firmes"
    )
    al_punt_firmes = obtener_alertas_anomalias_puntuales(df_res_f, filtro_confianza="firmes")
    c3a_f, c3b_f = obtener_alertas_candidatas(df_cand_f, df_tarifas, filtros.get("tarifa_override"))

    # Separar candidatas firmes vs indicativas
    c3a_firmes = c3a_f[~c3a_f["es_indicativa"]] if not c3a_f.empty else pd.DataFrame()
    c3b_firmes = c3b_f[~c3b_f["es_indicativa"]] if not c3b_f.empty else pd.DataFrame()

    lista_firmes = [al_sost_firmes, al_punt_firmes, c3a_firmes, c3b_firmes]
    df_firmes = pd.concat([d for d in lista_firmes if not d.empty], ignore_index=True) if any(not d.empty for d in lista_firmes) else pd.DataFrame()
    if not df_firmes.empty:
        df_firmes = df_firmes.sort_values("costo_cop", ascending=False).reset_index(drop=True)

    # 2. Alertas indicativas (baja confianza: refinación y filtros)
    al_sost_indicativas = calcular_alertas_exceso_sostenido(
        df_res_f, min_turnos, pct_umbral, min_costo, filtro_confianza="indicativas"
    )
    al_punt_indicativas = obtener_alertas_anomalias_puntuales(df_res_f, filtro_confianza="indicativas")
    c3a_indicativas = c3a_f[c3a_f["es_indicativa"]] if not c3a_f.empty else pd.DataFrame()
    c3b_indicativas = c3b_f[c3b_f["es_indicativa"]] if not c3b_f.empty else pd.DataFrame()

    lista_ind = [al_sost_indicativas, al_punt_indicativas, c3a_indicativas, c3b_indicativas]
    df_indicativas = pd.concat([d for d in lista_ind if not d.empty], ignore_index=True) if any(not d.empty for d in lista_ind) else pd.DataFrame()
    if not df_indicativas.empty:
        df_indicativas = df_indicativas.sort_values("costo_cop", ascending=False).reset_index(drop=True)

    # 3. Avisos de calidad (turnos incompletos)
    df_calidad = obtener_avisos_calidad_turnos_incompletos(df_dm_f)

    # Resumen métrico superior
    costo_tot_alertas_firmes = float(df_firmes["costo_cop"].sum()) if not df_firmes.empty else 0.0
    n_firmes = len(df_firmes)
    n_indicativas = len(df_indicativas)
    n_calidad = len(df_calidad)

    def resumen_procesos(df: pd.DataFrame) -> str:
        if df.empty or "proceso" not in df.columns:
            return "Sin alertas en el periodo"
        procesos = sorted(
            (str(proceso).strip() for proceso in df["proceso"].dropna().unique() if str(proceso).strip()),
            key=str.casefold,
        )
        if not procesos:
            return "Sin alertas en el periodo"
        return html.escape(", ".join(proceso.capitalize() for proceso in procesos))

    resumen_firmes = resumen_procesos(df_firmes)
    resumen_indicativas = resumen_procesos(df_indicativas)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Alertas Firmes</span></div>
                <div class="kpi-value" style="color:#ff6688">{n_firmes}</div>
                <div class="kpi-sub">{resumen_firmes}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with m2:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Costo Exceso Alertas</span></div>
                <div class="kpi-value" style="color:#ffc928">${costo_tot_alertas_firmes:,.0f} <span style="font-size:0.9rem">COP</span></div>
                <div class="kpi-sub">Suma de excesos firmes</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with m3:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Eventos Indicativos</span></div>
                <div class="kpi-value" style="color:#ffc928">{n_indicativas}</div>
                <div class="kpi-sub">{resumen_indicativas}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with m4:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title"><span>Avisos de Calidad</span></div>
                <div class="kpi-value" style="color:#52bfff">{n_calidad}</div>
                <div class="kpi-sub">Turnos con cobertura &lt; 75%</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Explicación de las reglas en un expander
    with st.expander("Criterios de Detección de Alertas y Justificación Metodológica", expanded=False):
        st.markdown(
            f"""
            | # | Tipo de Alerta | Regla Exacta Implementada | Tabla Fuente |
            |---|---|---|---|
            | **1** | **Exceso sostenido** | Rachas de turnos consecutivos con exceso &gt; **{pct_umbral:.0f} %** del esperado, duración &ge; **{min_turnos} turnos** y costo acumulado &ge; **${min_costo:,.0f} COP**. Excluye modelos con confianza baja. | `resultados_modelo` |
            | **2** | **Anomalía puntual** | Marcadas con `es_anomalia = 1` por ensamble de Isolation Forest y MAD robusto. | `resultados_modelo` |
            | **3a** | **Consumo en turno apagado** | Filas de `anomalias_candidatas_rc` con `z_robusto > 0`. | `anomalias_candidatas_rc` |
            | **3b** | **Parada inesperada** | Filas con `z_robusto < 0` (consumo casi cero donde típicamente opera alto, ej. filtros en festivos). | `anomalias_candidatas_rc` |
            | **4** | **Dato incompleto** | Turnos con `calidad_ok = 0` (cobertura &lt; 75 %). Aviso informativo de calidad, no de sobreconsumo. | `dataset_modelo` |
            | **Clasificación** | **Firmes / indicativas** | Ambas pestañas pueden incluir exceso sostenido, anomalías puntuales, consumo en turno apagado y paradas inesperadas. Se clasifican por confianza del modelo: alta o media = firme; baja = indicativa. | `resultados_modelo` y `anomalias_candidatas_rc` |
            | **Conteo de calidad** | **Avisos consolidados** | Se agrupan los registros incompletos por fecha y turno. Un aviso puede incluir varios procesos; el KPI cuenta turnos afectados, no registros proceso-turno. | `dataset_modelo` |

            *¿Por qué esta regla para exceso sostenido?* {texto('Los umbrales son parámetros editables, provisionales del equipo y sin respaldo de Clarios.', 'Los umbrales son parámetros ilustrativos editables; las alertas resultantes describen únicamente los datos sintéticos de esta demo.')}
            """
        )

    # Pestañas para Alertas Firmes, Indicativas y Calidad
    tab_firmes, tab_indicativas, tab_calidad = st.tabs([
        f"Alertas Firmes ({n_firmes})",
        f"Indicativas — Baja Confianza ({n_indicativas})",
        f"Avisos de Calidad ({n_calidad})"
    ])

    with tab_firmes:
        if df_firmes.empty:
            st.success("No se detectaron alertas firmes en el periodo y rango seleccionados.")
        else:
            render_tabla_alertas(df_firmes, es_indicativa=False)

    with tab_indicativas:
        render_callout(
            "> [!WARNING]\n" +
              texto("> **Indicativas:** son alertas de procesos cuyo modelo tiene confianza baja. Sirven de referencia, pero no conviene decidir solo con ellas.", "> **Demo sintética:** Las alertas ilustran reglas de detección sobre datos ficticios. No describen eventos de una planta real.")
        )
        if df_indicativas.empty:
            st.info("No hay eventos indicativos registrados en el periodo.")
        else:
            render_tabla_alertas(df_indicativas, es_indicativa=True)

    with tab_calidad:
        render_callout(
            "> [!NOTE]\n"
            "> **Aviso de Calidad de Datos:** Los turnos listados a continuación presentaron una cobertura efectiva "
            "menor al 75 % (por caídas del SCADA o huecos de telemetría). Por seguridad estadística, fueron **excluidos "
            "de los modelos** de consumo esperado."
        )
        if df_calidad.empty:
            st.success("Todos los turnos del periodo disponen de cobertura de datos completa (>= 75%).")
        else:
            df_calidad_graf = df_calidad.copy()
            df_calidad_graf["fecha_fin"] = pd.to_datetime(df_calidad_graf["fecha_fin"])
            df_calidad_graf["semana"] = (
                df_calidad_graf["fecha_fin"].dt.normalize()
                - pd.to_timedelta(df_calidad_graf["fecha_fin"].dt.weekday, unit="D")
            )
            conteo_turnos = (
                df_calidad_graf.groupby("turno", as_index=False)
                .size()
                .rename(columns={"size": "avisos"})
                .sort_values("turno")
            )
            conteo_semanal = (
                df_calidad_graf.groupby("semana", as_index=False)
                .size()
                .rename(columns={"size": "avisos"})
                .sort_values("semana")
            )

            c_turno, c_semana = st.columns(2)
            with c_turno:
                colores_turno = {"Turno 1": "#36d8dc", "Turno 2": "#8d68ff", "Turno 3": "#ff6688"}
                fig_turno = go.Figure(
                    go.Bar(
                        x=conteo_turnos["turno"],
                        y=conteo_turnos["avisos"],
                        marker_color=[colores_turno.get(turno, "#96a3c0") for turno in conteo_turnos["turno"]],
                        text=conteo_turnos["avisos"],
                        textposition="outside",
                        hovertemplate="%{x}: %{y} avisos<extra></extra>",
                    )
                )
                fig_turno = configurar_grafico(fig_turno, "Avisos por turno", altura=300)
                fig_turno.update_layout(
                    showlegend=False, hovermode="closest",
                    margin={"l": 35, "r": 25, "t": 55, "b": 40},
                )
                fig_turno.update_yaxes(title_text="Avisos", tickformat=".0f", rangemode="tozero")
                fig_turno.update_xaxes(title_text="")
                st.plotly_chart(
                    fig_turno, use_container_width=True, config={"displayModeBar": False},
                    key="grafica_calidad_por_turno",
                )

            with c_semana:
                fig_semana = go.Figure(
                    go.Scatter(
                        x=conteo_semanal["semana"],
                        y=conteo_semanal["avisos"],
                        mode="lines+markers",
                        line={"color": "#36d8dc", "width": 2.5},
                        marker={"size": 7},
                        hovertemplate="Semana del %{x|%d %b %Y}: %{y} avisos<extra></extra>",
                    )
                )
                fig_semana = configurar_grafico(fig_semana, "Evolución semanal de avisos", altura=300)
                fig_semana.update_layout(
                    showlegend=False, hovermode="closest",
                    margin={"l": 35, "r": 25, "t": 55, "b": 55},
                )
                fig_semana.update_yaxes(title_text="Avisos", tickformat=".0f", rangemode="tozero")
                fig_semana.update_xaxes(title_text="Semana (lunes)", tickformat="%d %b\n%Y")
                st.plotly_chart(
                    fig_semana, use_container_width=True, config={"displayModeBar": False},
                    key="grafica_calidad_evolucion_semanal",
                )

            st.dataframe(
                df_calidad[["fecha", "turno", "proceso", "tipo", "severidad", "detalle"]],
                hide_index=True,
                use_container_width=True
            )


def render_tabla_alertas(df_al: pd.DataFrame, es_indicativa: bool = False):
    """Renderiza la tabla interactiva de alertas ordenada por costo."""
    # Filtro rápido por proceso o tipo dentro de la pestaña
    c_f1, c_f2 = st.columns([1, 1])
    with c_f1:
        tipos_disp = ["Todos"] + sorted(df_al["tipo"].unique().tolist())
        sel_tipo = st.selectbox("Filtrar por Tipo:", tipos_disp, key=f"sel_tipo_{es_indicativa}")
    with c_f2:
        procs_disp = ["Todos"] + sorted(df_al["proceso"].unique().tolist())
        sel_proc = st.selectbox("Filtrar por Proceso:", procs_disp, key=f"sel_proc_{es_indicativa}")

    df_view = df_al.copy()
    if sel_tipo != "Todos":
        df_view = df_view[df_view["tipo"] == sel_tipo]
    if sel_proc != "Todos":
        df_view = df_view[df_view["proceso"] == sel_proc]

    if df_view.empty:
        st.info("No hay alertas que coincidan con los filtros seleccionados.")
    else:
        conteo_tipos = (
            df_view.groupby("tipo", as_index=False)
            .size()
            .rename(columns={"size": "cantidad"})
            .sort_values("cantidad", ascending=True)
        )
        conteo_severidad = df_view.assign(
            severidad_grafica=(
                df_view["severidad"].fillna("").astype(str).str.strip().str.capitalize()
            )
        )
        conteo_severidad["severidad_grafica"] = conteo_severidad["severidad_grafica"].replace(
            {"": "Sin clasificar"}
        )
        orden_severidad = {"Alta": 0, "Media": 1, "Baja": 2, "Sin clasificar": 3}
        conteo_severidad = (
            conteo_severidad.groupby("severidad_grafica", as_index=False)
            .size()
            .rename(columns={"size": "cantidad"})
        )
        conteo_severidad["_orden"] = conteo_severidad["severidad_grafica"].map(
            lambda valor: orden_severidad.get(valor, 4)
        )
        conteo_severidad = conteo_severidad.sort_values("_orden", ascending=False)
        altura_graficas = max(260, 68 * max(len(conteo_tipos), len(conteo_severidad)))

        c_tipo, c_severidad = st.columns(2)
        with c_tipo:
            fig_tipo = go.Figure(
                go.Bar(
                    x=conteo_tipos["cantidad"],
                    y=conteo_tipos["tipo"],
                    orientation="h",
                    marker_color="#8d68ff",
                    text=conteo_tipos["cantidad"],
                    textposition="outside",
                    hovertemplate="%{y}: %{x} alertas<extra></extra>",
                )
            )
            fig_tipo = configurar_grafico(
                fig_tipo, "Cantidad por tipo", altura=altura_graficas
            )
            fig_tipo.update_layout(
                showlegend=False, hovermode="closest",
                margin={"l": 25, "r": 30, "t": 55, "b": 35},
            )
            fig_tipo.update_xaxes(
                title_text="", showticklabels=False, ticks="", showgrid=False,
                zeroline=False, rangemode="tozero",
            )
            fig_tipo.update_yaxes(title_text="", categoryorder="total ascending")
            st.plotly_chart(
                fig_tipo,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"grafica_alertas_tipo_{'indicativa' if es_indicativa else 'firme'}",
            )

        with c_severidad:
            colores_severidad = {
                "Alta": "#ff6688", "Media": "#ffd36f", "Baja": "#8d9bb8",
                "Sin clasificar": "#aeb9d1",
            }
            fig_severidad = go.Figure(
                go.Bar(
                    x=conteo_severidad["cantidad"],
                    y=conteo_severidad["severidad_grafica"],
                    orientation="h",
                    marker_color=[
                        colores_severidad.get(valor, "#aeb9d1")
                        for valor in conteo_severidad["severidad_grafica"]
                    ],
                    text=conteo_severidad["cantidad"],
                    textposition="outside",
                    hovertemplate="%{y}: %{x} alertas<extra></extra>",
                )
            )
            fig_severidad = configurar_grafico(
                fig_severidad, "Cantidad por severidad", altura=altura_graficas
            )
            fig_severidad.update_layout(
                showlegend=False, hovermode="closest",
                margin={"l": 25, "r": 30, "t": 55, "b": 35},
            )
            fig_severidad.update_xaxes(
                title_text="", showticklabels=False, ticks="", showgrid=False,
                zeroline=False, rangemode="tozero",
            )
            fig_severidad.update_yaxes(
                title_text="", categoryorder="array",
                categoryarray=conteo_severidad["severidad_grafica"],
            )
            st.plotly_chart(
                fig_severidad,
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"grafica_alertas_severidad_{'indicativa' if es_indicativa else 'firme'}",
            )

    # Formatear columnas para visualización
    df_display = pd.DataFrame({
        "Fecha": df_view["fecha"],
        "Turno": df_view["turno"],
        "Proceso": df_view["proceso"].str.capitalize(),
        "Tipo de Alerta": df_view["tipo"],
        "Exceso (kWh)": df_view["exceso_kwh"].apply(lambda v: f"{v:+,.1f}"),
        "Impacto Económico": df_view["costo_cop"].apply(lambda v: f"${v:,.0f}"),
        "Severidad": df_view["severidad"].str.upper(),
    })

    def estilo_severidad(valor: str) -> str:
        estilos = {
            "ALTA": "color: #ff7d9f; background-color: #451b31; font-weight: 700",
            "MEDIA": "color: #ffd36f; background-color: #44351a; font-weight: 700",
            "BAJA": "color: #aab4d0; background-color: #252d49; font-weight: 700",
        }
        return estilos.get(valor, "color: #aab4d0")

    tabla = df_display.style.map(estilo_severidad, subset=["Severidad"])

    st.dataframe(
        tabla,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Impacto Económico": st.column_config.TextColumn(
                "Impacto Económico",
                help="Costo del kWh de exceso valorado según la tarifa aplicable"
            ),
            "Exceso (kWh)": st.column_config.TextColumn(
                "Exceso (kWh)",
                help="Diferencia neta sobre el consumo esperado o típico"
            )
        }
    )
