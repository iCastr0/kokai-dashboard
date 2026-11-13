"""6 · Reglas para decisiones futuras: precio de un plato nuevo, insumos expuestos y cuándo revisar la carta."""

import pandas as pd
import streamlit as st

from .. import analisis, datasets, ui
from ..config import ALZA_INSUMO_CLAVE, FC_PISO_NUEVO, IVA, REVISION_MESES
from ..fmt import clp, num, pct
from .parte2 import PARTE


def _mes_mas(info, meses: int) -> str:
    d = pd.Timestamp(info.hasta or info.generado) + pd.DateOffset(months=meses)
    return datasets.nombre_mes(d.date())


def _precio_nuevo(ctx):
    st.markdown("#### Precio de un plato nuevo")
    st.markdown(f"**Regla:** precio piso = costo de receta ÷ {num(FC_PISO_NUEVO, 2)} (sin IVA). Después se le suma "
                "el IVA, se lleva al precio de carta siguiente y se compara con la competencia y con los platos "
                "parecidos de la carta.")
    en = ctx.enriched
    c1, c2, c3, c4 = st.columns(4)
    costo = c1.number_input("Costo de receta ($, neto)", 0, 100_000, 1800, 50, key="pn_costo",
                            help="El «Costo neto» del plato en su hoja de la Maestra (incluye merma de receta).")
    fc = c2.number_input("Food cost objetivo (%)", 15.0, 50.0, FC_PISO_NUEVO * 100, 0.5, key="pn_fc") / 100
    cats = en.groupby("Categoria")["q"].sum().sort_values(ascending=False).index.tolist()
    cat = c3.selectbox("Categoría del plato", cats, key="pn_cat", format_func=lambda c: c.title())
    comp = c4.number_input("Precio de la competencia ($, con IVA)", 0, 200_000, 0, 100, key="pn_comp",
                           help="Opcional: un plato equivalente en otro restaurante.")
    if costo <= 0:
        ui.note("Ingresa el costo de receta para calcular el precio.")
        return
    r = analisis.precio_piso(costo, fc)
    k1, k2, k3 = st.columns(3)
    ui.kpi(k1, "Piso sin IVA", clp(round(r["neto"])), f"{clp(costo)} ÷ {num(fc, 2)}")
    ui.kpi(k2, "Piso con IVA", clp(round(r["bruto"])), f"× {num(1 + IVA, 2)}")
    ui.kpi(k3, "Precio de carta sugerido", clp(r["carta"]), f"food cost resultante {pct(r['fc_carta'])}",
           highlight=True)

    g = en[en["Categoria"] == cat]
    pares = g.groupby("_norm").agg(Plato=("Producto", "first"), Precio=("p", "mean"), Costo=("c", "mean"),
                                   Unidades=("q", "sum")).sort_values("Unidades", ascending=False)
    pares["Food cost"] = pares["Costo"] / (pares["Precio"] / (1 + IVA)) * 100
    lo, hi = pares["Precio"].min(), pares["Precio"].max()
    pos = ("bajo el más barato" if r["carta"] < lo else "sobre el más caro" if r["carta"] > hi
           else "dentro del rango")
    msgs = [f"En {cat.title()} los platos se venden entre {clp(round(lo))} y {clp(round(hi))}: el sugerido queda {pos}."]
    if comp:
        msgs.append(f"La competencia cobra {clp(comp)}: " + (
            "el piso queda **sobre** la competencia → revisar receta o porción antes de lanzarlo." if r["carta"] > comp
            else f"hay espacio entre {clp(r['carta'])} y {clp(comp)} para fijar el precio."))
    st.markdown(" ".join(msgs).replace("$", "\\$"))
    with st.expander(f"Ver los platos de {cat.title()} que ya se venden"):
        st.dataframe(pares.round({"Precio": 0, "Costo": 0}), hide_index=True, column_config={
            "Precio": st.column_config.NumberColumn("Precio promedio vendido ($)", format="localized"),
            "Costo": st.column_config.NumberColumn("Costo de receta ($)", format="localized"),
            "Unidades": st.column_config.NumberColumn(format="localized"),
            "Food cost": st.column_config.NumberColumn(format="%.1f%%")})
    st.caption("Calza con el modelo de precios de Kokai: en la Maestra (hoja PSalon) el «Precio Even teórico» "
               "también es costo ÷ food cost objetivo, hoy con 32 %.")


def _insumos(ctx):
    st.markdown("#### Insumos y platos expuestos")
    st.caption("Para saber qué revisar cuando llega una factura cara. Efecto directo: mismas unidades y mismos "
               "precios, solo cambia el costo del insumo.")
    en = ctx.enriched
    top = ctx.insumos[ctx.insumos["Insumo"] != "Platos sin receta desglosada"]["Insumo"].head(20).tolist()
    c1, c2 = st.columns([2, 3])
    ins = c1.selectbox("Insumo", top, key="ie_ins")
    alza = c2.slider("Cuánto sube su precio", 5, 50, int(ALZA_INSUMO_CLAVE * 100), 5, format="%d%%", key="ie_alza") / 100
    pts, platos = analisis.impacto_insumo(en, ins, alza)
    m = analisis.months(ctx.info)
    st.markdown(f"<div class='decision'>Si <b>{ins.lower()}</b> sube {num(alza * 100)} %, <b>{len(platos)} platos</b> "
                f"se ven afectados y el food cost total sube <b>~{num(pts, 2)} pts</b> (≈ "
                f"{clp(round(platos['costo_extra'].sum() / m, -3))} más al mes en insumos).</div>",
                unsafe_allow_html=True)
    t = platos.assign(peso_insumo=platos["peso_insumo"] * 100, fc_hoy=platos["fc_hoy"] * 100,
                      fc_nuevo=platos["fc_nuevo"] * 100, costo_extra=(platos["costo_extra"] / m).round(0))
    st.dataframe(t[["Plato", "Familia", "unidades", "peso_insumo", "fc_hoy", "fc_nuevo", "costo_extra"]],
                 hide_index=True, column_config={
                     "unidades": st.column_config.NumberColumn("Unidades/mes", format="localized"),
                     "peso_insumo": st.column_config.NumberColumn(f"% del costo que es {ins.lower()}", format="%.0f%%"),
                     "fc_hoy": st.column_config.NumberColumn("Food cost hoy", format="%.1f%%"),
                     "fc_nuevo": st.column_config.NumberColumn("Food cost con el alza", format="%.1f%%"),
                     "costo_extra": st.column_config.NumberColumn("Costo extra al mes ($)", format="localized")})

    st.markdown(f"##### Resumen: si cada insumo clave sube {num(ALZA_INSUMO_CLAVE * 100)} %")
    sens = analisis.sensibilidad(en, ALZA_INSUMO_CLAVE)
    st.dataframe(sens.assign(gasto=(sens["gasto"] / m).round(0), costo_extra=(sens["costo_extra"] / m).round(0))[
        ["Insumo", "gasto", "platos", "pts", "costo_extra"]], hide_index=True, column_config={
        "gasto": st.column_config.NumberColumn("Gasto al mes ($)", format="localized"),
        "platos": st.column_config.NumberColumn("Platos que lo usan"),
        "pts": st.column_config.NumberColumn("Food cost sube (pts)", format="+%.2f"),
        "costo_extra": st.column_config.NumberColumn("Costo extra al mes ($)", format="localized")})


def _cuando(ctx):
    st.markdown("#### Cuándo revisar la carta")
    sens = analisis.sensibilidad(ctx.enriched, ALZA_INSUMO_CLAVE, n=3)
    claves = ", ".join(sens["Insumo"].str.lower().iloc[:-1]) + " o " + sens["Insumo"].iloc[-1].lower()
    gatillos = [
        f"**Una vez por temporada** (cada {REVISION_MESES} meses). Próxima revisión: **{_mes_mas(ctx.info, REVISION_MESES)}**.",
        f"**Cuando un insumo clave sube más de {num(ALZA_INSUMO_CLAVE * 100)} %** ({claves}): cada uno mueve el food "
        f"cost entre {num(sens['pts'].min(), 2)} y {num(sens['pts'].max(), 2)} pts. Usar la tabla de arriba para "
        "ver qué platos revisar.",
        "**Cuando un indicador sale en rojo dos meses seguidos** en «Cómo saber si funcionó».",
        "**Cuando se agregan o se sacan platos, o cambia una receta** en la Maestra de costos.",
        "**Cuando llegue el resultado del piloto de precios**: reemplaza la reacción de los clientes que hoy se supone.",
    ]
    st.markdown("\n".join(f"{n}. {g}" for n, g in enumerate(gatillos, 1)))
    with st.expander("Cómo se recalcula todo"):
        st.markdown(
            "1. Si cambiaron precios de insumos o recetas, actualizar la Maestra de costos "
            "(`01_datos_originales/`).\n"
            "2. Barra lateral → **Actualizar desde Justo** → «Un mes completo» → el último mes cerrado.\n"
            "3. Ir a **Plan de acción** → **Calcular recomendaciones** (unos minutos, corre en segundo plano).\n"
            "4. Revisar el Resumen y el plan nuevo antes de cargar precios.")


def render(ctx):
    ui.page_header(PARTE, "Reglas para decisiones futuras", ctx.info,
                   "Reglas simples para seguir decidiendo sin el modelo: cómo ponerle precio a un plato nuevo, "
                   "qué revisar cuando sube un insumo y cuándo volver a mirar la carta.")
    _precio_nuevo(ctx)
    st.markdown("---")
    _insumos(ctx)
    st.markdown("---")
    _cuando(ctx)
