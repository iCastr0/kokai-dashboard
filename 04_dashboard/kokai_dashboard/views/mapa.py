"""3 · Mapa del menú (Kasavana-Smith, sin el nombre): cada cuadrante con lo que hay que hacer."""

import pandas as pd
import streamlit as st

from .. import charts, tables, ui
from ..config import CLASS_COLOR, CLASS_INFO, CLASS_LABEL, CLASS_RULE, CLASSES
from .resumen import PARTE


def _cards():
    for col, clase in zip(st.columns(4), CLASSES):
        que, hacer = CLASS_INFO[clase]
        col.markdown(
            f"<div class='cls-card' style='border-left-color:{CLASS_COLOR[clase]}'>"
            f"<div class='t'>{CLASS_LABEL[clase]}</div><div class='d'>{que}</div>"
            f"<div class='a'><b>Qué hacer:</b> {hacer}</div></div>",
            unsafe_allow_html=True)


def render(ctx):
    ui.page_header(PARTE, "Mapa del menú", ctx.info,
                   "Cada plato según cuánto se vende y cuánto margen deja. Describe la situación de hoy; no "
                   "depende de supuestos.")
    _cards()
    st.caption(CLASS_RULE)

    df = ctx.classified
    locales = sorted(df["Local"].unique())
    sel = st.radio("Local", ["Todos"] + locales, horizontal=True, key="map_local",
                   format_func=lambda s: s.replace("Kokai ", ""))
    view = df if sel == "Todos" else df[df["Local"] == sel]
    st.plotly_chart(charts.quadrant(view, locales if sel == "Todos" else [sel]))
    st.caption("Pasa el mouse sobre un punto para ver el plato. Las líneas punteadas son los umbrales de cada local.")

    plan_by_norm = ({("Kokai " + l, n): a for l, n, a in zip(ctx.plan["Local"], ctx.plan["_norm"], ctx.plan["Acción"])}
                    if ctx.has_plan else {})

    st.markdown("#### Platos de cada cuadrante")
    tabs = st.tabs([f"{CLASS_LABEL[c]} ({(view['clase'] == c).sum()})" for c in CLASSES])
    for tab, clase in zip(tabs, CLASSES):
        g = view[view["clase"] == clase].sort_values("q", ascending=False)
        with tab:
            st.caption(f"**Qué hacer:** {CLASS_INFO[clase][1]}"
                       + (" La acción de cada plato sale del plan (puede incluir alzas o cambios de visibilidad)."
                          if plan_by_norm else ""))
            t = g.assign(
                Local=g["Local"].str.replace("Kokai ", ""),
                **{"Acción sugerida": pd.Series([plan_by_norm.get(k) for k in zip(g["Local"], g["_norm"])],
                                                index=g.index).fillna(CLASS_INFO[clase][1])},
            )[["Producto", "Local", "q", "p", "c", "CM", "Acción sugerida"]].round({"p": 0, "c": 0, "CM": 0}).rename(columns={
                "Producto": "Plato", "q": "Unidades", "p": "Precio con IVA ($)", "c": "Costo receta ($)",
                "CM": "Margen por plato sin IVA ($)"})
            st.dataframe(t, hide_index=True, column_config={
                c: st.column_config.NumberColumn(format="localized")
                for c in ["Unidades", "Precio con IVA ($)", "Costo receta ($)", "Margen por plato sin IVA ($)"]})
