"""2 · Dónde se va la plata: food cost por local y familia, platos e insumos que más gastan."""

import streamlit as st

from .. import analisis, charts, ui
from ..fmt import clp, num, pct
from .resumen import PARTE


def _bars(df, label_col: str):
    return charts.hbar(
        df[label_col], df["costo"],
        text=[f"{clp(c)} · FC {pct(f)}" for c, f in zip(df["costo"], df["fc"])],
        hover=[f"Insumos: {clp(c)} ({pct(w)} del gasto)<br>Venta neta: {clp(v)}<br>Food cost: {pct(f)}"
               for c, w, v, f in zip(df["costo"], df["peso"], df["venta"], df["fc"])])


def render(ctx):
    ui.page_header(PARTE, "Dónde se va la plata", ctx.info,
                   "Gasto en insumos según las recetas, en pesos al mes. El food cost (FC) es "
                   "insumos ÷ venta neta de IVA.")
    en = ctx.enriched
    m = analisis.months(ctx.info)
    sc = en.assign(venta=en["venta"] / m, costo=en["costo"] / m)  # todo en pesos al mes

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Por local")
        loc = analisis.breakdown(sc, "Local")
        loc["Local"] = loc["Local"].str.replace("Kokai ", "")
        st.plotly_chart(_bars(loc, "Local"))
    with c2:
        st.markdown("#### Por familia de la carta")
        st.plotly_chart(_bars(analisis.breakdown(sc, "Familia"), "Familia"))
    fam = analisis.breakdown(sc, "Familia")
    st.caption(f"«{fam.iloc[0]['Familia']}» y «{fam.iloc[1]['Familia']}» se llevan el "
               f"{pct(fam['peso'].iloc[:2].sum(), 0)} del gasto en insumos.")

    st.markdown("#### Los 10 platos que más plata se llevan en insumos")
    st.caption("Ordenados por gasto total en pesos (costo de receta × unidades vendidas), no por %. Un plato "
               "con 40 % de food cost que casi no se vende importa menos que uno con 30 % que se vende todos "
               "los días.")
    top = analisis.top_platos(sc)
    st.plotly_chart(charts.hbar(
        top["Plato"], top["costo"],
        text=[f"{clp(c)} · {num(u)} unid. · FC {pct(f)}" for c, u, f in zip(top["costo"], top["unidades"], top["fc"])],
        hover=[f"{fa}<br>{pct(w)} de todo el gasto en insumos" for fa, w in zip(top["Familia"], top["peso"])]))
    st.caption(f"Estos 10 platos son el {pct(top['peso'].sum(), 0)} del gasto en insumos de toda la carta.")

    st.markdown("#### Los insumos donde se concentra el gasto")
    ins = ctx.insumos.assign(gasto=ctx.insumos["gasto"] / m)
    head = ins[ins["Insumo"] != "Platos sin receta desglosada"].head(12)
    st.plotly_chart(charts.hbar(
        head["Insumo"], head["gasto"], text=[f"{clp(g)} · {pct(w)}" for g, w in zip(head["gasto"], head["peso"])],
        hover=[f"{pct(w)} del gasto en insumos" for w in head["peso"]]))
    st.caption(f"Los 5 primeros suman el {pct(head['peso'].head(5).sum(), 0)} del gasto. Cada plato vendido se "
               "reparte en sus insumos según la receta de la Maestra de costos, incluyendo bases y salsas "
               "(el shari se cuenta como arroz, vinagre y azúcar).")
    with st.expander("Ver todos los insumos"):
        st.dataframe(ins.rename(columns={"gasto": "Gasto al mes ($)", "peso": "% del gasto"}).assign(
            **{"% del gasto": lambda d: d["% del gasto"] * 100}), hide_index=True,
            column_config={"Gasto al mes ($)": st.column_config.NumberColumn(format="localized"),
                           "% del gasto": st.column_config.NumberColumn(format="%.1f%%")})
