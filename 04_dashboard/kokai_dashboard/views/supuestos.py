"""7 · Supuestos y vigencia, en lenguaje simple."""

from datetime import date

import pandas as pd
import streamlit as st

from .. import analisis, datasets, maestra, ui
from ..config import (ALZA_INSUMO_CLAVE, CLASS_LABEL, CLASSES, DEFAULT_ELASTICITY, RANGE_HIGH, RANGE_LOW, RANGE_MID,
                      VIGENCIA_MESES)
from ..fmt import num, pct
from .parte2 import PARTE


def vence(info) -> date:
    """Último día del mes que cae VIGENCIA_MESES después del mes de los datos."""
    d = pd.Timestamp(info.hasta or info.generado) + pd.DateOffset(months=VIGENCIA_MESES)
    return (d + pd.offsets.MonthEnd(0)).date()


def _fecha_larga(d: date) -> str:
    return f"{d.day} de {datasets.MESES[d.month - 1]} de {d.year}"


def _baja(eps: float) -> str:
    return num((1 - 1.05 ** eps) * 100, 0) + " %"


def render(ctx):
    ui.page_header(PARTE, "Supuestos y vigencia", ctx.info,
                   "Qué hay detrás de los números y hasta cuándo sirven, en simple.")
    v = vence(ctx.info)
    vencido = date.today() > v
    c1, c2 = st.columns([1, 2])
    ui.kpi(c1, "Válido hasta", _fecha_larga(v), "como máximo" + (" · VENCIDO" if vencido else ""), highlight=True)
    c2.markdown(
        f"<div class='kpi'><div class='k'>O antes, si pasa cualquiera de estas cosas</div><div class='s' "
        f"style='font-size:.95rem;color:inherit;margin-top:.4rem'>• Cambia la carta (platos nuevos, platos que salen, "
        f"recetas distintas).<br>• Un insumo clave (salmón, palta, arroz…) sube más de "
        f"{num(ALZA_INSUMO_CLAVE * 100)} %.<br>• Llega el resultado del piloto de precios.</div></div>",
        unsafe_allow_html=True)
    if vencido:
        ui.warn("**Este plan ya venció.** Hay que recalcular con datos nuevos (ver «Reglas para decisiones futuras» "
                "→ «Cómo se recalcula todo»).")

    en = ctx.enriched
    st.markdown("#### Lo que se supuso")

    st.markdown(f"**1. Es un solo mes de datos ({ctx.info.mes}).** Son {num(en['q'].sum())} platos vendidos, "
                f"{en['_norm'].nunique()} platos distintos, en {en['Local'].nunique()} locales. Un mes puede tener "
                "cosas propias (feriados, clima, vacaciones). Por eso los resultados se revisan mes a mes en "
                "«Cómo saber si funcionó».")

    base = DEFAULT_ELASTICITY[RANGE_MID]
    reac = ", ".join(f"{CLASS_LABEL[c].lower()} ~{_baja(base[c])}" for c in CLASSES)
    lo, hi = DEFAULT_ELASTICITY[RANGE_LOW], DEFAULT_ELASTICITY[RANGE_HIGH]
    st.markdown(f"**2. La reacción de los clientes al precio es estimada, no medida.** Se supuso que si un plato "
                f"sube 5 %, su venta baja: {reac}. Como no está medido, se usó un rango: desde clientes que "
                f"reaccionan fuerte (caballos ~{_baja(lo['Caballo de batalla'])}) hasta clientes que casi no lo "
                f"notan (caballos ~{_baja(hi['Caballo de batalla'])}). El piloto de precios diseñado sirve "
                "justamente para medirlo.")

    est = analisis.platos_estimados(en)
    st.markdown(f"**3. Hay {len(est)} platos con costo estimado en vez de receta propia.** Algunos se cruzaron por "
                "un nombre parecido o con el promedio de variantes que Justo no distingue (por ejemplo, California "
                "Sake con sésamo o ciboulette); otros no tienen la receta desglosada en la Maestra. Juntos pesan "
                f"{pct(est['Peso en el costo'].sum())} del costo en insumos.")
    with st.expander(f"Ver los {len(est)} platos"):
        st.dataframe(est.assign(**{"Peso en el costo": est["Peso en el costo"] * 100}), hide_index=True,
                     column_config={"Unidades": st.column_config.NumberColumn(format="localized"),
                                    "Peso en el costo": st.column_config.NumberColumn(format="%.1f%%")})

    f0, f1 = maestra.fechas_precios()
    if f1:
        fecha = _fecha_larga(f1) if f0 == f1 else f"entre el {_fecha_larga(f0)} y el {_fecha_larga(f1)}"
        meses = (pd.Timestamp(ctx.info.hasta or ctx.info.generado) - pd.Timestamp(f1)).days // 30
        st.markdown(f"**4. Los precios de los insumos son los de la Maestra de costos, actualizados al {fecha}**"
                    + (f", unos {meses} meses antes de las ventas. Si los insumos subieron desde entonces, el food "
                       "cost real es algo mayor que el que se muestra; vale la pena actualizar la hoja "
                       "«Ingredientes» con las facturas recientes." if meses >= 3 else "."))

    st.markdown("**5. Qué incluye y qué no incluye este food cost.** Es el costo de los insumos según la receta "
                "de cada plato (con los envases que están en la receta y la merma de receta) dividido por la venta "
                "registrada en Justo, sin IVA. No incluye merma de bodega que no esté en las recetas, comida del "
                "personal ni cortesías. Por eso puede no coincidir con un food cost calculado desde la contabilidad.")

    p = ctx.params
    st.markdown(f"**6. Los límites que se le pusieron a las recomendaciones.** Ningún plato sube más de "
                f"{pct(p['bound_delta'][1], 0)}; la visibilidad de un plato cambia como máximo ±{pct(p['bound_u'][1], 0)}; "
                f"las unidades totales no pueden caer más de {pct(p['max_drop'], 0)} y el margen en pesos no puede "
                "bajar. Las decisiones están pensadas juntas: aplicar solo una parte cambia el resultado.")
