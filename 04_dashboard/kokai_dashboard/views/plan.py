"""4 · Plan de acción: el optimizador traducido a decisiones, con precios de carta por canal."""

import streamlit as st

from . import calculo
from .. import analisis, export, maestra, tables, ui
from ..config import ASSUMPTION_WARNING, CLASS_LABEL, CLASSES, RANGE_HIGH, RANGE_LOW
from ..fmt import clp, clp_md, num
from .resumen import PARTE

PRIO_INFO = {
    "Hacer ya": "Juntos explican la mayor parte de la baja del food cost.",
    "Probar": "Cambios en estrellas y otras alzas: probar primero en un local y mirar las unidades.",
    "Opcional": "Aportes chicos, sobre todo cambios de visibilidad.",
}


def _flecha(a, b) -> str:
    if a != a:  # NaN: el plato no está en ese canal
        return "—"
    return num(a) if b == a else f"{num(a)} → {num(b)}"


def render(ctx):
    ui.page_header(PARTE, "Plan de acción", ctx.info)
    if not ctx.has_plan:
        calculo.render_panel(ctx.classified, ctx.info, ctx.params, where="plan")
        return
    plan = ctx.plan[ctx.plan["Prioridad"] != "—"]

    cols = st.columns(3)
    for col, prio in zip(cols, analisis.PRIORIDADES):
        s = plan[plan["Prioridad"] == prio]
        ui.kpi(col, prio, f"{len(s)} cambios", f"{num(s['Efecto FC (pts)'].sum(), 2)} pts de food cost de receta · "
               + PRIO_INFO[prio], highlight=prio == "Hacer ya")
    st.write("")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    prios = f1.multiselect("Prioridad", analisis.PRIORIDADES, default=["Hacer ya", "Probar"], key="plan_prio")
    locales = sorted(plan["Local"].unique())
    locs = f2.multiselect("Local", locales, default=locales, key="plan_local")
    cuad = f3.multiselect("Cuadrante", [CLASS_LABEL[c] for c in CLASSES],
                          default=[CLASS_LABEL[c] for c in CLASSES], key="plan_cuad")
    q = f4.text_input("Buscar plato", key="plan_search")
    t = plan[plan["Prioridad"].isin(prios) & plan["Local"].isin(locs) & plan["Cuadrante"].isin(cuad)]
    if q:
        t = t[t["Plato"].str.contains(q, case=False, na=False)]

    view = t.assign(**{ch: [_flecha(a, b) for a, b in zip(t[f"{ch} actual"], t[f"{ch} sugerido"])]
                       for ch in maestra.CHANNELS})
    view = view[["Prioridad", "Plato", "Local", "Cuadrante", "Acción", *maestra.CHANNELS, "Efecto FC (pts)", "Efecto $/mes",
                 "Unidades/mes"]].round({"Efecto $/mes": 0, "Unidades/mes": 0})
    st.dataframe(
        tables.style_class(view), hide_index=True,
        column_config={
            "Acción": st.column_config.TextColumn(width="medium"),
            **{ch: st.column_config.TextColumn(f"{ch} ($)", help="Precio actual → sugerido, con IVA, redondeado a "
                                                                 "precio de carta. «—»: no está en ese canal.")
               for ch in maestra.CHANNELS},
            "Efecto FC (pts)": st.column_config.NumberColumn(
                format="%+.3f", help="Cuánto mueve este plato el food cost total, en puntos (negativo = baja)."),
            "Efecto $/mes": st.column_config.NumberColumn(
                format="localized", help="Margen adicional al mes de este plato (venta neta − insumos), caso "
                                         "central. Si pierde visibilidad, su venta pasa a otros platos: aquí resta, "
                                         "allá suma."),
            "Unidades/mes": st.column_config.NumberColumn(format="localized"),
        })
    if t.empty:
        ui.note("Ningún plato coincide con los filtros.")
        return

    lo, hi = t["_min"].sum(), t["_max"].sum()
    st.caption(f"{len(t)} cambios en {t['Plato'].nunique()} platos · food cost de receta {num(t['Efecto FC (pts)'].sum(), 2)} pts · margen ≈ "
               f"{clp_md(round(t['Efecto $/mes'].sum(), -3))} al mes (entre {clp_md(round(min(lo, hi), -3))} y "
               f"{clp_md(round(max(lo, hi), -3))} según cuánto reaccionen los clientes). Las decisiones se pensaron "
               "juntas: aplicar solo una parte cambia el resultado.")
    ui.warn(ASSUMPTION_WARNING)

    xls = t[["Prioridad", "Plato", "Local", "SKU", "Cuadrante", "Acción",
             *[f"{ch} {k}" for ch in maestra.CHANNELS for k in ("actual", "sugerido")],
             "Efecto FC (pts)", "Efecto $/mes", "_min", "_max", "Unidades/mes"]].rename(columns={
        "_min": f"Efecto $/mes ({RANGE_LOW})", "_max": f"Efecto $/mes ({RANGE_HIGH})"})
    notas = [
        "RECOMENDACIONES basadas en una reacción de los clientes al precio ASUMIDA (piloto aún no ejecutado).",
        f"Datos de {ctx.info.mes} ({ctx.info.path.name}).",
        "Precios con IVA, redondeados a precio de carta (terminados en 90). Una decisión por plato y local, "
        "tal como la entrega el modelo.",
        "Efecto $/mes = margen adicional (venta neta − costo de insumos), caso central.",
        f"Filtros: prioridad = {', '.join(prios)}; locales = {', '.join(locs)}; cuadrante = {', '.join(cuad)}" + (f"; búsqueda = {q}" if q else ""),
    ]
    st.download_button("Descargar plan en Excel (para cargar precios)", export.to_excel(xls, notas),
                       "plan_de_accion_kokai.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
