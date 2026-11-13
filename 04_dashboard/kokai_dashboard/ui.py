"""Estilo global (CSS) y avisos sobrios. Sin emojis ni íconos: la jerarquía la dan tipografía, bordes y el
acento naranja, usado con moderación."""

import streamlit as st

from .config import ACCENT, NAVY, SILVER, SLATE

_CSS = f"""
<style>
  .block-container {{ padding-top: 2.2rem; max-width: 1320px; }}
  h1 {{ font-size: 1.75rem; font-weight: 600; letter-spacing: -0.01em; margin-bottom: .25rem; }}
  h2, h3, h4, h5 {{ font-weight: 600; letter-spacing: -0.005em; }}
  [data-testid="stCaptionContainer"] {{ color: {SLATE}; }}

  /* Barra de datos activos */
  .ds-bar {{ display: flex; flex-wrap: wrap; gap: .4rem 2.2rem; padding: .7rem 0 .9rem 0;
             border-top: 1px solid {SILVER}; border-bottom: 1px solid {SILVER}; margin: .6rem 0 1.1rem 0; }}
  .ds-bar .k {{ display: block; font-size: .68rem; letter-spacing: .09em; text-transform: uppercase; color: {SLATE}; }}
  .ds-bar .v {{ font-size: .95rem; font-weight: 500; color: {NAVY}; }}

  /* Pestañas */
  .stTabs [data-baseweb="tab-list"] {{ gap: 1.8rem; border-bottom: 1px solid {SILVER}; }}
  .stTabs [data-baseweb="tab"] {{ padding: .55rem 0; color: {SLATE}; font-weight: 500; background: transparent; }}
  .stTabs [aria-selected="true"] {{ color: {NAVY}; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background-color: {ACCENT}; height: 2px; }}
  .stTabs [data-baseweb="tab-border"] {{ display: none; }}

  /* KPIs */
  [data-testid="stMetric"] {{ border: 1px solid {SILVER}; border-radius: 3px; padding: .9rem 1.1rem; }}
  [data-testid="stMetricLabel"] p {{ color: {SLATE}; text-transform: uppercase; letter-spacing: .07em; font-size: .72rem; }}
  [data-testid="stMetricValue"] {{ font-weight: 600; font-variant-numeric: tabular-nums; }}

  /* Barra lateral, expanders, botones */
  section[data-testid="stSidebar"] {{ border-right: 1px solid {SILVER}; }}
  .brand {{ font-size: 1.05rem; font-weight: 700; letter-spacing: .28em; color: {NAVY};
            padding-bottom: .6rem; border-bottom: 2px solid {ACCENT}; display: inline-block; margin-bottom: 1rem; }}
  [data-testid="stExpander"] {{ border: 1px solid {SILVER}; border-radius: 3px; }}
  .stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {{
      border-radius: 3px; font-weight: 500; }}
  .stAppDeployButton {{ display: none; }}

  /* Avisos: borde lateral, sin íconos ni colores de semáforo */
  [class*="st-key-callout-"] {{ border-left: 3px solid {SLATE}; background: rgba(191,192,192,.20);
                                padding: .8rem 1.1rem; border-radius: 2px; margin: .4rem 0 .9rem 0; }}
  [class*="st-key-callout-"] p {{ margin: 0; }}
  [class*="st-key-callout-warn"], [class*="st-key-callout-error"] {{ border-left-color: {ACCENT}; }}
  [class*="st-key-callout-error"] {{ background: rgba(239,131,84,.10); }}

  /* Tarjetas de clase */
  .cls-card {{ border: 1px solid {SILVER}; border-left-width: 4px; border-radius: 3px; padding: .8rem 1rem; height: 100%; margin-bottom: 1.1rem; }}
  .cls-card .t {{ font-weight: 600; color: {NAVY}; margin-bottom: .25rem; }}
  .cls-card .d {{ color: {NAVY}; font-size: .92rem; margin-bottom: .45rem; }}
  .cls-card .a {{ color: {SLATE}; font-size: .85rem; }}

  /* Encabezado de página: parte + fecha de los datos bien visible */
  .pg-part {{ font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: {SLATE}; margin-bottom: -.2rem; }}
  .data-date {{ display: inline-block; border: 1px solid {NAVY}; border-radius: 3px; padding: .3rem .75rem;
                font-weight: 600; color: {NAVY}; margin: .2rem 0 1rem 0; font-size: .95rem; }}
  .data-date span {{ font-weight: 400; color: {SLATE}; }}

  /* Tarjetas de cifras del resumen */
  .kpi {{ border: 1px solid {SILVER}; border-radius: 3px; padding: .9rem 1.1rem; min-height: 8.2rem; }}
  .kpi.hl {{ border-color: {NAVY}; border-top: 3px solid {ACCENT}; }}
  .kpi .k {{ font-size: .72rem; letter-spacing: .07em; text-transform: uppercase; color: {SLATE}; }}
  .kpi .v {{ font-size: 1.75rem; font-weight: 600; color: {NAVY}; font-variant-numeric: tabular-nums; line-height: 1.25; margin: .2rem 0; }}
  .kpi .s {{ font-size: .86rem; color: {SLATE}; }}
  .sem {{ display: inline-block; border: 1px solid {SILVER}; border-radius: 3px; padding: .1rem .55rem;
          font-size: .8rem; font-weight: 600; color: {NAVY}; white-space: nowrap; }}
  .sem i {{ font-style: normal; margin-right: .3rem; }}
  .ind {{ border: 1px solid {SILVER}; border-radius: 3px; padding: 1rem 1.15rem .6rem 1.15rem; margin-bottom: .4rem; }}
  .ind .t {{ display: flex; justify-content: space-between; align-items: center; gap: .6rem; }}
  .ind .t b {{ color: {NAVY}; font-size: 1rem; }}
  .ind .v {{ font-size: 1.6rem; font-weight: 600; color: {NAVY}; font-variant-numeric: tabular-nums; margin: .35rem 0 0 0; }}
  .ind .s, .ind .r {{ font-size: .86rem; color: {SLATE}; margin: .25rem 0; }}
  .ind .r b {{ color: {NAVY}; }}
  .decision {{ border-left: 3px solid {ACCENT}; padding: .15rem 0 .15rem .9rem; margin: .55rem 0; color: {NAVY}; }}
</style>
"""


def apply():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.session_state["_callout_n"] = 0


def _callout(tone: str, msg: str):
    n = st.session_state["_callout_n"] = st.session_state.get("_callout_n", 0) + 1
    with st.container(key=f"callout-{tone}-{n}"):
        st.markdown(msg)


def note(msg: str):
    _callout("note", msg)


def warn(msg: str):
    _callout("warn", msg)


def error(msg: str):
    _callout("error", msg)


def dataset_bar(info) -> str:
    items = [("Datos generados", f"{info.generado:%d/%m/%Y %H:%M}"), ("Período de ventas", info.periodo),
             ("Fuente", info.fuente)]
    cells = "".join(f'<div><span class="k">{k}</span><span class="v">{v}</span></div>' for k, v in items)
    return f'<div class="ds-bar">{cells}</div>'


def page_header(parte: str, title: str, info, subtitle: str | None = None):
    st.markdown(f"<div class='pg-part'>{parte}</div>", unsafe_allow_html=True)
    st.title(title)
    st.markdown(f"<div class='data-date'>Datos de {info.mes} <span>· {info.fuente} · generado "
                f"{info.generado:%d/%m/%Y}</span></div>", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def kpi(col, label: str, value: str, sub: str = "", highlight: bool = False):
    col.markdown(f"<div class='kpi{' hl' if highlight else ''}'><div class='k'>{label}</div>"
                 f"<div class='v'>{value}</div><div class='s'>{sub}</div></div>", unsafe_allow_html=True)


def semaforo(estado: str | None) -> str:
    """Insignia de estado: ícono + texto (el color nunca va solo)."""
    from .config import STATUS
    if estado is None:
        return "<span class='sem'><i>○</i>Falta el dato</span>"
    color, icon, label = STATUS[estado]
    return f"<span class='sem'><i style='color:{color}'>{icon}</i>{label}</span>"


def semaforo_txt(estado: str | None) -> str:
    """La misma insignia en texto plano, para tablas."""
    from .config import STATUS
    return "○ Falta el dato" if estado is None else f"{STATUS[estado][1]} {STATUS[estado][2]}"
