"""Página "Monitoreo en vivo" del dashboard (simulada).

Se ejecuta sola:   streamlit run dashboard/pagina_monitoreo.py
o se integra en el dashboard con `mostrar()`. Cada 5 segundos llegan una o más horas de lecturas del SCADA (inventadas), se limpian
con las reglas del proyecto, se cierran los turnos y se recalculan el semáforo y las alertas. El motor está en `monitoreo.py`.
Con CLARIOS_DATOS_REALES definida la historia de partida es la real (solo en local); si no, es sintética. Las lecturas que llegan son siempre inventadas.
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

from monitoreo import HORAS_TURNO, PROCESOS, TIPOS_EVENTO, MotorEnVivo  # noqa: E402

COLORES = {"verde": "#2e9e5b", "amarillo": "#e0a800", "rojo": "#d64545", "gris": "#8a8f98"}
ETIQUETA_EVENTO = {"exceso": "Exceso de consumo sostenido", "parada": "Parada inesperada", "congelamiento": "Congelamiento del SCADA", "reinicio": "Reinicio de un contador"}
INTERVALO_S = 5


def _motor(guion: bool = False, semilla: int = 2026) -> MotorEnVivo:
    if "motor" not in st.session_state or st.session_state.get("reiniciar"):
        st.session_state["motor"] = MotorEnVivo(semilla=semilla, guion=guion)
        st.session_state["reiniciar"] = False
    return st.session_state["motor"]


def _barra_lateral(motor: MotorEnVivo) -> None:
    with st.container(border=True):
        st.markdown("**Controles de la simulación**")
        c1, c2, c3 = st.columns([1, 1, 2])
        if c1.button("▶ Iniciar" if not st.session_state.get("corriendo") else "⏸ Pausar", width="stretch"):
            st.session_state["corriendo"] = not st.session_state.get("corriendo", False)
            st.rerun()
        if c2.button("↺ Reiniciar", width="stretch"):
            st.session_state["reiniciar"] = True
            st.session_state["corriendo"] = False
            st.rerun()
        with c3:
            st.session_state["horas_por_paso"] = st.select_slider("Horas simuladas por actualización", options=[1, 2, 4, 8], value=st.session_state.get("horas_por_paso", 1),
                                                                  help=f"Cada {INTERVALO_S} s de reloj real llegan estas horas de lecturas del SCADA.")
        st.checkbox("Guion de la demostración al reiniciar", key="guion",
                    help="Programa un congelamiento del SCADA, un exceso sostenido en el horno, un reinicio de contador y una parada inesperada.")

        st.markdown("Inyectar un evento ahora")
        e1, e2, e3, e4 = st.columns([2, 2, 1, 1], vertical_alignment="bottom")
        tipo = e1.selectbox("Evento", TIPOS_EVENTO, format_func=ETIQUETA_EVENTO.get)
        proceso = None if tipo == "congelamiento" else e2.selectbox("Proceso", PROCESOS)
        horas = None if tipo == "reinicio" else e3.number_input("Horas", 1, 72, {"exceso": 24, "parada": 4, "congelamiento": 5}[tipo])
        if e4.button("Inyectar", width="stretch"):
            motor.inyectar(tipo, proceso, int(horas) if horas else None)
            st.toast(f"{ETIQUETA_EVENTO[tipo]} inyectado")

        with st.expander("Parámetros editables"):
            p = motor.p
            p["tarifa"] = st.number_input("Tarifa (COP/kWh)", 100.0, 2000.0, float(p["tarifa"]), help="config.yaml, tarifas.tarifa_kwh_cop")
            p["alerta_turnos"] = st.number_input("Turnos seguidos para exceso sostenido", 1, 10, int(p["alerta_turnos"]))
            p["alerta_pct"] = st.number_input("Exceso mínimo (%)", 1.0, 100.0, float(p["alerta_pct"]))
            p["alerta_costo_cop"] = st.number_input("Costo mínimo del episodio (COP)", 0.0, 5_000_000.0, float(p["alerta_costo_cop"]), step=50_000.0)
            p["semaforo_amarillo"] = st.number_input("Semáforo amarillo desde (%)", 0.0, 50.0, float(p["semaforo_amarillo"]))
            p["semaforo_rojo"] = st.number_input("Semáforo rojo desde (%)", 0.0, 100.0, float(p["semaforo_rojo"]))
            st.caption("Los umbrales son provisionales del equipo, sin respaldo de Clarios. Los turnos (06-14, 14-22, 22-06) son un supuesto.")


def _tarjetas(motor: MotorEnVivo) -> None:
    sem, cur = motor.semaforo().set_index("proceso"), motor.turno_en_curso().set_index("proceso")
    cols = st.columns(len(PROCESOS))
    for col, p in zip(cols, PROCESOS):
        s, c = sem.loc[p], cur.loc[p]
        with col, st.container(border=True):
            st.markdown(f"<span style='color:{COLORES[s.color]};font-size:1.3em'>●</span> **{p.capitalize()}**", unsafe_allow_html=True)
            st.metric("Exceso neto (últimos 7 días)", f"{s.exceso_pct:+.1f} %" if pd.notna(s.exceso_pct) else "—",
                      f"{s.costo_cop / 1e6:,.1f} M COP" if s.costo_cop else None, delta_color="inverse", help="Suma del real menos suma del esperado sobre los últimos 21 turnos válidos. Sale del modelo entrenado.")
            frac = min(c.horas / HORAS_TURNO, 1.0)
            st.progress(frac, text=f"Turno {int(c.turno)} en curso: {int(c.horas)}/{HORAS_TURNO} h")
            if c.horas and pd.notna(c.razon):
                st.caption(f"{c.kwh_acumulado:,.0f} kWh de {c.esperado_acumulado:,.0f} esperados a esta hora ({c.razon:.0%})")
            elif c.horas_sin_dato:
                st.caption(f"{int(c.horas_sin_dato)} h sin dato todavía")
            if s.indicativo:
                st.caption("Indicativo", help="Modelo de confianza baja: sirve de referencia, pero no conviene decidir solo con este dato.")
            if s.color == "gris":
                st.caption("Dato incompleto")


def _grafica(motor: MotorEnVivo) -> None:
    proceso = st.selectbox("Proceso", PROCESOS, key="proceso_grafica")
    d = motor.serie_horaria(48)
    d = d[d["proceso"] == proceso]
    fig = go.Figure()
    fig.add_scatter(x=d["hora"], y=d["esperado"], name="Esperado (modelo)", line=dict(color="#8a8f98", dash="dash"))
    ok = d[d["calidad"] == "ok"]
    fig.add_scatter(x=ok["hora"], y=ok["kwh"], name="Real (medido)", mode="lines+markers", line=dict(color="#2a6fdb"))
    est = d[d["calidad"] == "estimado"]
    if len(est):
        fig.add_scatter(x=est["hora"], y=est["kwh"], name="Estimado (repartido)", mode="markers", marker=dict(color="#e0a800", size=9, symbol="diamond"))
    for _, r in d[d["calidad"].isin(["congelado", "reinicio"])].iterrows():
        fig.add_vrect(x0=r["hora"], x1=r["hora"] + pd.Timedelta(hours=1), fillcolor="#8a8f98", opacity=0.25, line_width=0)
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="kWh por hora", legend=dict(orientation="h", y=-0.22),
                      title=f"{proceso.capitalize()} · últimas 48 h (zonas grises: sin dato)")
    st.plotly_chart(fig, width="stretch")


def _alertas(motor: MotorEnVivo) -> None:
    a = motor.alertas()
    nuevas = a[a["nueva"]]
    st.markdown(f"**Alertas desde que empezó el monitoreo ({len(nuevas)})**")
    if nuevas.empty:
        st.success("Sin alertas nuevas.")
        return
    vista = nuevas.assign(fecha=nuevas["fecha_turno"].dt.strftime("%d %b"), costo=(nuevas["costo_cop"] / 1000).round(0), proceso=nuevas["proceso"].str.capitalize(),
                          indicativa=nuevas["indicativa"].map({True: "indicativa", False: ""}))
    st.dataframe(vista[["tipo", "fecha", "turno", "proceso", "detalle", "costo", "indicativa"]].rename(columns={"costo": "costo (miles COP)"}),
                 hide_index=True, width="stretch", height=300)


def _panel(motor: MotorEnVivo) -> None:
    if st.session_state.get("corriendo"):
        motor.avanzar(st.session_state.get("horas_por_paso", 1))
    st.caption(f"Hora simulada: **{motor.ahora:%d %b %Y %H:%M}** · {'🟢 en vivo' if st.session_state.get('corriendo') else '⏸ en pausa'} · {motor.horas_simuladas} h recibidas · "
               f"historia de partida: **{motor.fuente}** · las lecturas nuevas son simuladas")
    _tarjetas(motor)
    izq, der = st.columns([3, 2])
    with izq:
        _grafica(motor)
    with der:
        _alertas(motor)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Calidad de los datos: lo que hizo la limpieza**")
        b = motor.bitacora_df()
        st.dataframe(b.assign(hora=b["hora"].dt.strftime("%d %b %H:%M")) if len(b) else b, hide_index=True, width="stretch", height=240)
    with c2:
        st.markdown("**Últimos turnos cerrados**")
        t = motor.turnos[motor.turnos["estado"] != "historico"].sort_values(["fecha_turno", "turno"], ascending=False).head(30)
        if t.empty:
            st.info("Aún no cierra ningún turno.")
        else:
            st.dataframe(t.assign(fecha_turno=t["fecha_turno"].dt.strftime("%d %b"), proceso=t["proceso"].str.capitalize()).round(1)[
                ["fecha_turno", "turno", "proceso", "kwh_real", "kwh_esperado", "exceso_pct", "estado"]], hide_index=True, width="stretch", height=240)


def mostrar() -> None:
    st.title("Monitoreo en vivo")
    st.caption("Simulación de la llegada de datos del SCADA cada pocas horas: lectura de contadores → limpieza → cierre de turno → comparación con el consumo esperado → semáforo y alertas.")
    motor = _motor(guion=st.session_state.get("guion", False))
    _barra_lateral(motor)
    corriendo = bool(st.session_state.get("corriendo"))
    st.fragment(run_every=INTERVALO_S if corriendo else None)(_panel)(motor)


if __name__ == "__main__":
    st.set_page_config(page_title="Monitoreo en vivo", layout="wide")
    mostrar()
