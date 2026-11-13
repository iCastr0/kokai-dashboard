"""1 · Resumen: todo lo que hay que saber en una sola pantalla."""

import re

import streamlit as st

from . import calculo
from .. import analisis, ui
from ..config import RANGE_HIGH, RANGE_LOW
from ..fmt import clp, num, pct
from .supuestos import _fecha_larga, vence

PARTE = "Parte 1 · Qué decidir ahora"


def _miles(x: float) -> str:
    return clp(round(x, -3))


def _mil(x: float) -> str:
    """$278 mil / $1,2 millones: cifras cortas para las tarjetas."""
    return f"${num(x / 1e6, 1)} millones" if abs(x) >= 1e6 else f"${num(x / 1e3)} mil"


def render(ctx):
    ui.page_header(PARTE, "Resumen", ctx.info)
    en = ctx.enriched
    venta_mes = en["venta"].sum() / analisis.months(ctx.info)
    fc_hoy, meta = analisis.food_cost(en), ctx.fc_meta

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.35])
    ui.kpi(c1, "Food cost hoy", pct(fc_hoy), f"≈ {_miles(fc_hoy * venta_mes)} al mes en insumos")
    if meta is None:
        ui.kpi(c2, "Meta", "Por definir", "se fija en la barra lateral («Meta de food cost»)")
    elif fc_hoy > meta:
        ui.kpi(c2, "Meta", pct(meta), f"faltan {num((fc_hoy - meta) * 100, 1)} pts ≈ "
               f"{_miles((fc_hoy - meta) * venta_mes)} al mes")
    else:
        ui.kpi(c2, "Meta", pct(meta), "ya se cumple hoy")
    if not ctx.has_plan:
        ui.kpi(c3, "Con el plan", "—", "falta calcular el plan")
        ui.kpi(c4, "Ahorro potencial", "—", "")
        calculo.render_panel(ctx.classified, ctx.info, ctx.params, where="resumen")
        return

    lo, hi = ctx.totals[RANGE_LOW], ctx.totals[RANGE_HIGH]
    fc_a, fc_b = sorted([lo["fc1"], hi["fc1"]])
    fc_txt = pct(fc_a) if round(fc_a, 3) == round(fc_b, 3) else f"{num(fc_a * 100, 1)}–{pct(fc_b)}"
    ui.kpi(c3, "Con el plan", fc_txt, f"{num((fc_hoy - fc_b) * 100, 1)} pts menos que hoy"
           + ("" if meta is None else " · dentro de la meta" if fc_b <= meta else " · aún sobre la meta"))
    a, b = sorted([lo["margen1"] - lo["margen0"], hi["margen1"] - hi["margen0"]])
    ui.kpi(c4, "Ahorro potencial", f"{_mil(a)} – {_mil(b)}",
           "más margen al mes (venta neta − insumos)", highlight=True)

    st.markdown("#### Qué recomendamos hacer")
    for i, d in enumerate(analisis.decisiones(ctx.plan, ctx.insumos), 1):
        d = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", d)
        st.markdown(f"<div class='decision'>{i}. {d}</div>", unsafe_allow_html=True)
    st.caption("El detalle plato por plato, con los precios por canal listos para cargar, está en «Plan de acción». "
               f"Vigente hasta el {_fecha_larga(vence(ctx.info))} o hasta que cambie la carta o un insumo clave "
               "suba más de 10 % (ver «Supuestos y vigencia»).")

    st.markdown("---")
    st.caption(
        "**Cómo leer estas cifras.** Food cost = costo de insumos según las recetas de la Maestra ÷ venta neta de "
        "IVA registrada en Justo, con el método del proyecto. El rango del ahorro va de clientes que reaccionan "
        "fuerte al alza (cifra menor) a clientes que casi no la notan (cifra mayor): la reacción al precio "
        "todavía no está medida.")
