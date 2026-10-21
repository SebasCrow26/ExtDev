"""estilos.py — Componentes visuales modernos, temas de Plotly y CSS para Streamlit."""
import re
import plotly.graph_objects as go
import streamlit as st


def render_callout(markdown: str):
    """Renderiza admoniciones Markdown como avisos nativos de Streamlit."""
    lineas = []
    tipo = "NOTE"
    for linea in markdown.strip().splitlines():
        texto = linea.strip()
        if texto.startswith(">"):
            texto = texto[1:].lstrip()
        coincidencia = re.fullmatch(r"\[!(NOTE|WARNING|IMPORTANT|TIP|CAUTION)\]", texto, re.IGNORECASE)
        if coincidencia:
            tipo = coincidencia.group(1).upper()
            continue
        lineas.append(texto)

    contenido = "\n".join(lineas).strip()
    if tipo in {"WARNING", "CAUTION"}:
        st.warning(contenido)
    else:
        st.info(contenido)


def aplicar_estilos_css():
    """Inyecta CSS moderno para interfaz ejecutiva de alto impacto."""
    st.markdown(
        """
        <style>
        /* Import Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Oculta el menú y Deploy sin tapar el control para expandir el sidebar. */
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenu"],
        #MainMenu {
            display: none !important;
            visibility: hidden !important;
        }

        /* Top header bar */
        .clarios-header {
            padding: 0.3rem 0 0.65rem;
            background: transparent;
            color: #231F20;
            margin-bottom: 1rem;
            border: 0;
            box-shadow: none;
        }
        .clarios-header h1 {
            color: #231F20 !important;
            font-size: 2rem !important;
            font-weight: 700 !important;
            margin: 0 !important;
            padding: 0 !important;
            letter-spacing: -0.02em;
        }
        .clarios-header p {
            color: #536078 !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 0.78rem !important;
            margin: 0 0 0.45rem !important;
            letter-spacing: 0.02em;
        }
        .clarios-header::after {
            display: block;
            width: 4.4rem;
            height: 4px;
            margin-top: 0.7rem;
            background: #212492;
            content: "";
        }

        /* Banner de alcance de medidores */
        .alcance-disclaimer {
            background-color: rgba(245, 158, 11, 0.12);
            border: 1px solid rgba(245, 158, 11, 0.4);
            border-left: 5px solid #f59e0b;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 1.25rem;
            color: #fef3c7;
            font-size: 0.88rem;
        }

        /* Tarjeta moderna tipo KPI */
        .kpi-card {
            background: #ffffff;
            border: 1px solid #deded9;
            border-radius: 10px;
            padding: 1rem 1.2rem;
            transition: all 0.2s ease;
            box-shadow: 0 1px 3px rgba(35,31,32,0.05);
            margin-bottom: 0.75rem;
        }
        .kpi-card:hover {
            border-color: #b9bad9;
            transform: translateY(-2px);
            box-shadow: 0 5px 14px rgba(35,31,32,0.08);
        }
        .kpi-title {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #536078;
            margin-bottom: 0.3rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .kpi-value {
            font-size: 1.65rem;
            font-weight: 700;
            color: #231F20;
            line-height: 1.2;
            font-family: 'Inter', sans-serif;
        }
        .kpi-sub {
            font-size: 0.82rem;
            color: #596273;
            margin-top: 0.35rem;
        }

        .kpi-overview {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            overflow: hidden;
            margin: 0.8rem 0 0.35rem;
            border: 1px solid #deded9;
            border-radius: 10px;
            background: #ffffff;
        }
        .kpi-overview-item {
            min-width: 0;
            padding: 1.05rem 1.25rem;
            border-right: 1px solid #ecebe7;
        }
        .kpi-overview-item:last-child { border-right: 0; }
        .kpi-overview-label {
            margin-bottom: 0.35rem;
            color: #536078;
            font-size: 0.78rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .kpi-overview-value {
            color: #101828;
            font-size: clamp(1.2rem, 1.6vw, 1.8rem);
            font-weight: 700;
            line-height: 1.25;
            white-space: nowrap;
        }
        .kpi-overview-sub, .kpi-note {
            margin-top: 0.35rem;
            color: #596273;
            font-size: 0.82rem;
        }
        @media (max-width: 900px) {
            .kpi-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .kpi-overview-item:nth-child(2) { border-right: 0; }
            .kpi-overview-item:nth-child(-n+2) { border-bottom: 1px solid #ecebe7; }
        }

        /* Badges de Semáforo */
        .badge-semaforo {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        .badge-rojo {
            background-color: #fbe7e3;
            color: #b83f2b;
            border: 1px solid #efb8ae;
        }
        .badge-amarillo {
            background-color: #fff2cf;
            color: #231F20;
            border: 1px solid #d9a227;
        }
        .badge-verde {
            background-color: #e3f0e8;
            color: #347255;
            border: 1px solid #b7d5c2;
        }
        .badge-gris {
            background-color: #eef0f2;
            color: #596273;
            border: 1px solid #d5d9df;
        }

        /* Badges de Confianza */
        .badge-confianza {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .conf-alta { background: #ececff; color: #30328a; border: 1px solid #c7c8ef; }
        .conf-media { background: #f1eaf8; color: #65428a; border: 1px solid #d9c9e9; }
        .conf-baja { background: #fff2cf; color: #231F20; border: 1px solid #d9a227; }

        /* Tarjeta de proceso */
        .proceso-card {
            background: #ffffff;
            border: 1px solid #deded9;
            border-radius: 12px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            box-shadow: 0 1px 3px rgba(35,31,32,0.05);
        }
        .proceso-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid #ecebe7;
        }
        .proceso-nombre {
            font-size: 1.25rem;
            font-weight: 700;
            color: #101828;
            text-transform: capitalize;
        }

        /* Panel "El indicador engaña" */
        .panel-engano {
            background: linear-gradient(135deg, #1e1e38 0%, #2a1b3d 100%);
            border: 2px solid #818cf8;
            border-radius: 12px;
            padding: 1.5rem;
            margin: 1.5rem 0;
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.15);
        }

        /* Barra lateral inspirada en la referencia */
        section[data-testid="stSidebar"] {
            background: #050711;
            border-right: 1px solid #171d35;
            container-type: inline-size;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            color: #ffffff;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #e7e2ef;
        }
        .sidebar-brand {
            display: flex;
            min-height: 62px;
            align-items: center;
            justify-content: center;
            margin: 0 0 0.55rem;
            border-radius: 10px;
            background: #ffffff;
            color: #212492;
            font-size: 1.7rem;
            font-weight: 800;
            letter-spacing: -0.06em;
        }
        .sidebar-team {
            margin: 0 0 1.5rem;
            padding: 0.65rem 0.5rem;
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 8px;
            color: #d6c8e8;
            font-size: 0.78rem;
            font-weight: 600;
            text-align: center;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }
        section[data-testid="stSidebar"] [data-testid="stImage"] {
            margin-bottom: 0.55rem;
            padding: 0;
            border-radius: 0;
            background: transparent;
        }
        .sidebar-section-title {
            margin: 1.2rem 0 0.55rem;
            color: #bba9d5;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] {
            gap: 0.2rem;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label {
            min-height: 42px;
            padding: 0.35rem 0.55rem;
            border-radius: 7px;
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: rgba(255,255,255,0.14);
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label p {
            color: #ffffff !important;
            font-weight: 600;
        }
        section[data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.14);
        }
        section[data-testid="stSidebar"] button {
            border-color: rgba(255,255,255,0.2);
        }
        section[data-testid="stSidebar"] [data-baseweb="tag"] {
            background: #3639a0;
        }
        section.main div[data-testid="stButton"] button {
            border: 1px solid #deded9;
            background: #ffffff;
            color: #212492;
            font-weight: 600;
        }
        section.main div[data-testid="stButton"] button:hover {
            border-color: #212492;
            background: #f4f4fb;
            color: #212492;
        }
        /* Sidebar footer */
        .sidebar-footer {
            margin-top: 2rem;
            padding-top: .75rem;
            border-top: 1px solid #334155;
            font-size: 0.58rem;
            color: #929dbb;
            font-weight: 600;
            letter-spacing: .1em;
            text-transform: uppercase;
        }
        .sidebar-developed {
            position: fixed;
            left: 1rem;
            bottom: 1.4rem;
            z-index: 1000;
            width: calc(100cqw - 2rem);
            box-sizing: border-box;
            padding-top: .65rem;
            border-top: 1px solid #202747;
        }
        .sidebar-developed span {
            display: block;
            margin-bottom: .45rem;
            color: #929dbb;
            font-size: .56rem;
            font-weight: 600;
            letter-spacing: .1em;
            text-transform: uppercase;
        }
        .sidebar-developed img {
            display: block;
            width: 138px;
            height: 38px;
            object-fit: cover;
            object-position: center;
            padding: 0;
            border-radius: 0;
            background: transparent;
        }
        .sidebar-team-fallback {
            color: #e8eaf6;
            font-size: .72rem;
        }

        /* Interfaz ejecutiva oscura inspirada en la referencia del dashboard. */
        .stApp, [data-testid="stAppViewContainer"] {
            background: #080b18;
            color: #e8eaf6;
        }
        section.main > div {
            background: #080b18;
        }
        section.main [data-testid="stMarkdownContainer"] p,
        section.main [data-testid="stMarkdownContainer"] li,
        section.main label,
        section.main [data-testid="stCaptionContainer"] {
            color: #aab4d0;
        }
        section.main h1, section.main h2, section.main h3, section.main h4 {
            color: #f3f5ff;
        }
        /* Filtros de fecha de Gas: barra anclada al viewport durante el scroll. */
        .st-key-gas-filter-bar {
            position: fixed;
            top: 3.5rem;
            left: clamp(22rem, 24vw, 27rem);
            right: 3rem;
            width: auto !important;
            max-width: calc(100vw - 30rem);
            min-width: 0;
            box-sizing: border-box;
            z-index: 10000;
            padding: 0.55rem 0.9rem 0.15rem;
            background: rgba(8, 11, 24, 0.97);
            border: 1px solid #29345a;
            border-radius: 0.6rem;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.24);
            backdrop-filter: blur(10px);
        }
        .st-key-gas-filter-bar [data-testid="stHorizontalBlock"] {
            width: 100%;
            min-width: 0;
            flex-wrap: nowrap;
        }
        .st-key-gas-filter-bar [data-testid="column"] {
            min-width: 0 !important;
        }
        body:has(section[data-testid="stSidebar"][aria-expanded="false"]) .st-key-gas-filter-bar {
            left: 4rem;
            max-width: calc(100vw - 8rem);
        }
        @media (max-width: 700px) {
            .st-key-gas-filter-bar {
                top: 3.25rem;
                left: 0.5rem;
                right: 0.5rem;
                max-width: calc(100vw - 1rem);
                padding: 0.5rem 0.65rem 0.15rem;
            }
            body:has(section[data-testid="stSidebar"][aria-expanded="false"]) .st-key-gas-filter-bar {
                left: 0.5rem;
                max-width: calc(100vw - 1rem);
            }
        }
        .stApp [data-baseweb="select"] > div,
        .stApp [data-testid="stDateInput"] input,
        .stApp [data-testid="stTextInput"] input,
        .stApp [data-testid="stNumberInput"] input {
            background: #10162b;
            color: #e8eaf6;
            border-color: #29345a;
            color-scheme: dark;
        }
        .stApp [data-baseweb="tag"] {
            background: #212492;
            color: #eef0ff;
        }
        .stApp [role="listbox"], .stApp [role="option"] {
            background: #10162b;
            color: #e8eaf6;
        }
        section[data-testid="stSidebar"] {
            background: #050711;
            border-right: 1px solid #171d35;
        }
        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: linear-gradient(90deg, rgba(33,36,146,.58), rgba(33,36,146,.16));
            border: 1px solid rgba(62,231,226,.16);
        }
        .clarios-header {
            padding: 0.35rem 0 0.6rem;
            color: #f4f6ff;
            margin-bottom: 0.6rem;
        }
        .clarios-header h1 { color: #f4f6ff !important; font-size: 1.65rem !important; }
        .clarios-header p { color: #aab4d0 !important; }
        .clarios-header::after {
            width: 0;
            height: 0;
            margin: 0;
        }
        .alcance-disclaimer {
            color: #b9c5dd;
            background: linear-gradient(90deg, rgba(18, 34, 55, .92), rgba(13, 24, 42, .92));
            border: 1px solid #172943;
            border-left: 3px solid #36d8dc;
            border-radius: 8px;
            padding: .55rem .8rem;
            margin: .25rem 0 .9rem;
            font-size: .78rem;
        }
        .kpi-overview {
            gap: .65rem;
            overflow: visible;
            margin: .65rem 0 .35rem;
            border: 0;
            background: transparent;
        }
        .kpi-overview-item {
            padding: .85rem .95rem;
            border: 1px solid #202747;
            border-radius: 11px;
            background: linear-gradient(145deg, #121831, #0d1226);
            box-shadow: 0 7px 24px rgba(0,0,0,.16);
        }
        .kpi-overview-item:last-child { border-right: 1px solid #202747; }
        .kpi-card {
            min-height: 108px;
            padding: .85rem .95rem;
            border: 1px solid #202747;
            border-radius: 10px;
            background: linear-gradient(145deg, #121831, #0d1226);
            box-shadow: 0 7px 24px rgba(0,0,0,.16);
        }
        .kpi-title { color: #929dbb; font-size: .67rem; }
        .kpi-value { color: #f3f5ff; font-size: 1.55rem; }
        .kpi-sub { color: #8e9ab9; font-size: .7rem; }
        section.main button[data-baseweb="tab"] {
            color: #9ca9c8;
            border-bottom-color: #202747;
        }
        section.main button[data-baseweb="tab"][aria-selected="true"] {
            color: #f3f5ff;
            border-bottom-color: #ff6688;
        }
        section.main [data-testid="stExpander"] {
            border: 1px solid #202747;
            border-radius: 9px;
            background: #0e152b;
        }
        section.main [data-testid="stExpander"] summary,
        section.main [data-testid="stExpander"] summary p {
            color: #e8eaf6;
        }
        section.main [data-testid="stMarkdownContainer"] table th,
        section.main [data-testid="stMarkdownContainer"] table td {
            color: #cbd4eb;
            background: #10162b;
            border-color: #252d49;
        }
        .filter-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: .65rem;
            margin: .45rem 0 .8rem;
            padding: .55rem .75rem;
            border: 1px solid #1c2645;
            border-radius: 9px;
            background: #0e152b;
            color: #aab4d0;
            font-size: .72rem;
        }
        .filter-strip strong { color: #36d8dc; font-size: .65rem; letter-spacing: .08em; }
        .filter-strip b { color: #e5eaff; font-weight: 600; }
        .filter-count { margin-left: auto; color: #55e0bd; }
        .method-banner {
            margin: .35rem 0 .8rem;
            padding: .7rem .85rem;
            border: 1px solid #1c3653;
            border-left: 3px solid #36d8dc;
            border-radius: 8px;
            background: linear-gradient(100deg, #0c1a2c, #0d1428);
            color: #aebbd4;
            font-size: .75rem;
            line-height: 1.55;
        }
        .method-banner strong { color: #68e5e5; font-size: .67rem; letter-spacing: .06em; }
        .pron-metric-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .6rem;
            margin: .55rem 0 .8rem;
        }
        .pron-metric-grid > div {
            min-width: 0;
            padding: .65rem .8rem;
            border: 1px solid #202747;
            border-radius: 9px;
            background: linear-gradient(145deg, #121831, #0d1226);
        }
        .pron-metric-grid small, .pron-metric-grid strong { display: block; }
        .pron-metric-grid small { color: #929dbb; font-size: .62rem; text-transform: uppercase; letter-spacing: .04em; }
        .pron-metric-grid strong { margin-top: .25rem; color: #f3f5ff; font-size: 1rem; white-space: nowrap; }
        .pron-metric-grid i { color: #8e9ab9; font-size: .66rem; font-style: normal; }
        .pron-result-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: .65rem;
            margin: .55rem 0 .75rem;
        }
        .pron-result-card {
            min-width: 0;
            padding: .85rem .9rem;
            border: 1px solid #39466d;
            border-top: 3px solid #36d8dc;
            border-radius: 9px;
            background: linear-gradient(145deg, #151f3d, #10162b);
        }
        .pron-result-card small {
            display: block;
            color: #d5def0;
            font-size: .7rem;
            font-weight: 600;
            letter-spacing: .025em;
        }
        .pron-result-card strong {
            display: block;
            margin-top: .35rem;
            color: #ffffff;
            font-size: clamp(1rem, 1.55vw, 1.45rem);
            font-weight: 750;
            line-height: 1.2;
            overflow-wrap: anywhere;
        }
        .pron-result-card:nth-child(2) { border-top-color: #8d68ff; }
        .pron-result-card:nth-child(3) { border-top-color: #36d8dc; }
        .pron-result-card:nth-child(4) { border-top-color: #ffd36f; }
        .pron-result-card i { color: #d5def0; font-size: .78rem; font-style: normal; font-weight: 500; }
        .pron-result-meta {
            margin: .35rem 0;
            color: #eef3ff;
            font-size: .88rem;
            font-weight: 600;
        }
        .pron-result-note {
            margin: .2rem 0 .7rem;
            color: #c3cde2;
            font-size: .78rem;
        }
        .plant-kpi-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: .65rem;
            margin: .45rem 0 1.05rem;
        }
        .plant-kpi-card, .plant-budget-card {
            min-width: 0;
            padding: .85rem .95rem;
            border: 1px solid #202747;
            border-radius: 10px;
            background: linear-gradient(145deg, #121831, #0d1226);
            box-shadow: 0 7px 24px rgba(0,0,0,.14);
        }
        .plant-kpi-card small, .plant-budget-card small {
            display: block;
            color: #929dbb;
            font-size: .64rem;
            letter-spacing: .04em;
            text-transform: uppercase;
        }
        .plant-kpi-card strong, .plant-budget-card > strong {
            display: block;
            margin: .3rem 0 .18rem;
            color: #f3f5ff;
            font-size: 1.25rem;
            line-height: 1.25;
        }
        .plant-kpi-card i, .plant-budget-card i {
            color: #8e9ab9;
            font-size: .68rem;
            font-style: normal;
            font-weight: 400;
        }
        .plant-kpi-card p, .plant-budget-card p {
            margin: .38rem 0 0;
            color: #8995b3;
            font-size: .66rem;
        }
        .plant-delta {
            display: inline-block;
            padding: .16rem .4rem;
            border-radius: 5px;
            font-size: .62rem;
            font-weight: 700;
        }
        .plant-delta.down, .plant-budget-status.good { color: #42dfb3; background: rgba(27,198,160,.12); }
        .plant-delta.up, .plant-budget-status.bad { color: #ff7d9f; background: rgba(255,60,105,.13); }
        .plant-delta.neutral { color: #aab4d0; background: rgba(130,145,174,.13); }
        .plant-budget-card { min-height: 228px; }
        .plant-budget-card hr { border-color: #202747; margin: .8rem 0; }
        .plant-budget-card > strong { font-size: 1.5rem; }
        .plant-budget-status {
            display: inline-block;
            margin-top: .55rem;
            padding: .3rem .45rem;
            border-radius: 5px;
            font-size: .68rem;
            font-weight: 700;
        }
        @media (max-width: 800px) {
            .plant-kpi-grid { grid-template-columns: 1fr; }
            .pron-metric-grid { grid-template-columns: 1fr; }
            .pron-result-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        section.main [data-testid="stMetric"] {
            padding: .75rem;
            border: 1px solid #202747;
            border-radius: 9px;
            background: #11172e;
        }
        section.main [data-testid="stMetricLabel"] { color: #929dbb; }
        section.main [data-testid="stMetricValue"] { color: #f3f5ff; }
        .detalle-kpi {
            min-height: 82px;
            margin: .25rem 0 .8rem;
            padding: .75rem 1rem;
            border: 1px solid #29345a;
            border-radius: 9px;
            background: #111831;
        }
        .detalle-kpi span {
            display: block;
            margin-bottom: .25rem;
            color: #b8c4e2;
            font-size: .78rem;
        }
        .detalle-kpi strong {
            display: block;
            color: #f5f7ff;
            font-size: 1.45rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .detalle-kpi strong.exceso { color: #ff718f; }
        .detalle-kpi strong.costo { color: #ffd36f; }
        section.main [data-testid="stForm"] {
            padding: .85rem;
            border: 1px solid #202747;
            border-radius: 10px;
            background: #0d1328;
        }
        .kpi-overview-label { color: #929dbb; font-size: .68rem; }
        .kpi-overview-value { color: #f3f5ff; font-size: clamp(1.15rem, 1.35vw, 1.55rem); }
        .kpi-overview-sub, .kpi-note { color: #aab4d0; font-size: .72rem; }
        .proceso-card {
            min-height: 255px;
            padding: .9rem;
            border: 1px solid #202747;
            border-radius: 11px;
            background: linear-gradient(155deg, #121831 0%, #0e1328 100%);
            box-shadow: 0 7px 24px rgba(0,0,0,.18);
        }
        .proceso-card div[style*="color:#596273"],
        .proceso-card span[style*="color:#596273"] { color: #aab4d0 !important; }
        .proceso-card div[style*="color:#231F20"],
        .proceso-card strong[style*="color:#231F20"] { color: #e8eaf6 !important; }
        .proceso-card .card-meta-value { color: #f3f5ff !important; font-weight: 700; }
        .proceso-card div[style*="border-top:1px dashed"] { border-top-color: #202747 !important; }
        .proceso-header { border-bottom-color: #202747; margin-bottom: .65rem; padding-bottom: .55rem; }
        .proceso-nombre { color: #f3f5ff; font-size: 1rem; }
        .badge-semaforo { font-size: .66rem; padding: 3px 7px; }
        .badge-rojo { background: rgba(210,65,104,.18); color: #ff7d9f; border-color: rgba(210,65,104,.3); }
        .badge-amarillo { background: rgba(217,164,65,.18); color: #ffd36f; border-color: rgba(217,164,65,.34); }
        .badge-verde { background: rgba(20,190,158,.16); color: #55e0bd; border-color: rgba(20,190,158,.3); }
        .badge-gris { background: rgba(130,145,174,.15); color: #aeb9d1; border-color: rgba(130,145,174,.28); }
        .badge-confianza, .conf-alta, .conf-media, .conf-baja {
            background: rgba(33,36,146,.28);
            color: #bec8ff;
            border: 1px solid rgba(117,125,255,.22);
        }
        div[data-testid="stButton"] button,
        button[data-testid*="baseButton"] {
            background-color: #151c37 !important;
            background-image: none !important;
            border: 1px solid #29345a !important;
            color: #cbd5f1 !important;
            box-shadow: none !important;
        }
        div[data-testid="stButton"] button p,
        div[data-testid="stButton"] button span {
            color: #cbd5f1 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stButton"] button:hover,
        button[data-testid*="baseButton"]:hover {
            background-color: #202947 !important;
            border-color: #46547d !important;
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button {
            min-height: 40px;
            justify-content: flex-start !important;
            padding: 0.35rem 0.65rem !important;
            background: transparent !important;
            border: 1px solid transparent !important;
            box-shadow: none !important;
            color: #e8eaf6 !important;
            text-align: left !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button p,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button span {
            width: 100%;
            color: inherit !important;
            text-align: left !important;
            font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(90deg, rgba(33,36,146,.58), rgba(33,36,146,.16)) !important;
            border-color: rgba(62,231,226,.22) !important;
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
            background: rgba(255,255,255,.08) !important;
            border-color: rgba(255,255,255,.12) !important;
            color: #ffffff !important;
        }
        /* Acción principal para ejecutar la simulación semanal. */
        div.st-key-sim_calcular_semana_v2 button {
            background-color: #c9364f !important;
            border-color: #e35b70 !important;
            color: #ffffff !important;
            box-shadow: 0 2px 8px rgba(201,54,79,.25) !important;
        }
        div.st-key-sim_calcular_semana_v2 button p,
        div.st-key-sim_calcular_semana_v2 button span {
            color: #ffffff !important;
        }
        div.st-key-sim_calcular_semana_v2 button:hover {
            background-color: #a92d43 !important;
            border-color: #f07888 !important;
        }
        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] [data-baseweb="select"] > div,
        section[data-testid="stSidebar"] [data-testid="stDateInput"] input {
            background: #10162b;
            color: #e8eaf6;
            border-color: #29345a;
        }
        [data-testid="stDataFrame"], [data-testid="stTable"] {
            background: #10162b;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def configurar_grafico(fig: go.Figure, titulo: str = "", altura: int = 400) -> go.Figure:
    """Aplica el tema claro y la paleta Clarios a cualquier gráfico Plotly."""
    fig.update_layout(
        title={
            "text": titulo,
            "y": 0.95,
            "x": 0.02,
            "xanchor": "left",
            "yanchor": "top",
            "font": {"size": 15, "color": "#f3f5ff", "family": "Inter, sans-serif"}
        },
        template="plotly_dark",
        colorway=["#36d8dc", "#8d68ff", "#96a3c0", "#1bc6a0", "#ff6688"],
        paper_bgcolor="#10162b",
        plot_bgcolor="#10162b",
        height=altura,
        margin={"l": 45, "r": 35, "t": 50, "b": 45},
        hovermode="x unified",
        hoverlabel={"bgcolor": "#080b18", "font_color": "#ffffff", "font_size": 12, "font_family": "Inter"},
        font={"family": "Inter, sans-serif", "color": "#aab4d0", "size": 11},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1.0,
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"size": 11, "color": "#aab4d0"}
        },
        xaxis={
            "gridcolor": "#252d49",
            "zerolinecolor": "#55617d",
            "showline": True,
            "linecolor": "#252d49"
        },
        yaxis={
            "gridcolor": "#252d49",
            "zerolinecolor": "#55617d",
            "showline": True,
            "linecolor": "#252d49"
        }
    )
    return fig


def render_header(titulo: str, subtitulo: str = ""):
    """Renderiza un encabezado claro con contexto y título."""
    st.markdown(
        f"""
        <div class="clarios-header">
            <p>{subtitulo}</p>
            <h1>{titulo}</h1>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_alcance_rc_banner():
    """Aclara que esta interfaz usa exclusivamente datos sintéticos."""
    st.markdown(
        '<div class="alcance-disclaimer"><strong>DEMO SINTÉTICA:</strong> Las cifras, fechas, metas y alertas son ilustrativas; no representan mediciones ni resultados operativos reales.</div>',
        unsafe_allow_html=True
    )

