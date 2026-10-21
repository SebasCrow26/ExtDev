"""Punto de entrada del dashboard de monitoreo energético Clarios."""
from __future__ import annotations

import datetime
import base64
from pathlib import Path
import sys

import streamlit as st

# Asegurar importación de src
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dashboard.datos import get_config
from dashboard import pagina_monitoreo
from dashboard.estilos import aplicar_estilos_css
from dashboard.paginas import (
    alertas,
    calidad,
    detalle,
    gas,
    plantas,
    pronostico,
    resumen,
)


def _seleccionar_pagina(pagina: str) -> None:
    st.session_state["pagina_dashboard_activa"] = pagina

# Configuración de página de Streamlit
st.set_page_config(
    page_title="Clarios — Monitoreo Energético",
    page_icon=str(RAIZ / "dashboard" / "assets" / "icono_clarios_favicon.png"),
    layout="wide",
    initial_sidebar_state="expanded"
)

# Aplicar diseño CSS moderno
aplicar_estilos_css()


def main():
    cfg = get_config()

    # ==========================================================================
    # BARRA LATERAL (SIDEBAR)
    # ==========================================================================
    with st.sidebar:
        # Logos opcionales: agrega los archivos en src/dashboard/assets/.
        assets = Path(__file__).resolve().parent / "assets"
        logo_clarios = assets / "logo_clarios_sidebar.png"
        logo_equipo = assets / "logo_equipo_sidebar.png"
        if logo_clarios.is_file():
            st.image(str(logo_clarios), use_container_width=True)
        else:
            st.markdown('<div class="sidebar-brand">CLARIOS</div>', unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # NAVEGACIÓN PRINCIPAL
        # ----------------------------------------------------------------------
        st.markdown('<div class="sidebar-section-title">MONITOREO ENERGÉTICO</div>', unsafe_allow_html=True)
        paginas_opciones = {
            "3.1 Resumen RC": ("Resumen", resumen.render),
            "3.2 Detalle Proceso": ("Detalle por proceso", detalle.render),
            "3.3 Alertas": ("Alertas", alertas.render),
            "3.4 Pronóstico": ("Pronóstico", pronostico.render),
            "3.5 Plantas Mensual": ("Plantas", plantas.render),
            "3.6 Gas Refinación": ("Gas de refinación", gas.render),
            "3.7 Calidad & Supuestos": ("Calidad y supuestos", calidad.render),
            "3.8 Monitoreo en vivo": ("Monitoreo en vivo", lambda filtros: pagina_monitoreo.mostrar()),
        }
        seleccion = st.session_state.get("pagina_dashboard_activa", "3.1 Resumen RC")
        for clave_pagina, (etiqueta, _) in paginas_opciones.items():
            st.button(
                etiqueta,
                key=f"sidebar_nav_{clave_pagina}",
                type="primary" if seleccion == clave_pagina else "secondary",
                use_container_width=True,
                on_click=_seleccionar_pagina,
                args=(clave_pagina,),
            )
        # Pie de sidebar
        if logo_equipo.is_file():
            equipo_data = base64.b64encode(logo_equipo.read_bytes()).decode("ascii")
            logo_equipo_html = f'<img src="data:image/png;base64,{equipo_data}" alt="ExtDev x Clarios">'
        else:
            logo_equipo_html = '<strong class="sidebar-team-fallback">ExtDev</strong>'
        st.markdown(
            f'<div class="sidebar-developed"><span>Desarrollado por</span>{logo_equipo_html}</div>',
            unsafe_allow_html=True,
        )

    # Cada pantalla conserva sus filtros locales; estos valores son solo defaults.
    filtros = {
        "fecha_inicio": datetime.date(2026, 9, 1),
        "fecha_fin": datetime.date(2026, 9, 30),
        "turnos": [1, 2, 3],
        "procesos": ["triturado", "horno", "refinacion", "filtros", "ptari"],
        "tarifa_override": None,
        "semaforo_verde": float(cfg.get("semaforo", {}).get("verde_hasta_pct", 5.0)),
        "semaforo_amarillo": float(cfg.get("semaforo", {}).get("amarillo_hasta_pct", 10.0)),
        "min_turnos_alerta": 3,
        "pct_umbral_alerta": 10.0,
        "min_costo_alerta": 100000.0,
    }
    # Renderizar la página seleccionada
    nombre_pagina, render_func = paginas_opciones[seleccion]
    render_func(filtros)


if __name__ == "__main__":
    main()

