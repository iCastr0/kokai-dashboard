import pandas as pd
import streamlit as st

from . import calculo
from .. import charts, jobs, ui
from ..config import CLASSES, DEFAULT_ELASTICITY, DEFAULT_PARAMS, SCENARIO_INFO, SCENARIOS
from ..fmt import clp, num, pct


def _escenarios(classified, results: dict, params: dict, info):
    st.markdown("#### Escenarios del optimizador")
    st.caption("Lo que entrega el modelo en cada escenario de reacción al precio, sin redondear precios ni "
               "unificar locales (por eso difiere un poco del plan). Venta y margen netos de IVA, del período.")
    for s in SCENARIOS:
        st.markdown(f"- **{s}:** {SCENARIO_INFO[s]}")
    with st.expander("Ver la elasticidad supuesta por cuadrante"):
        st.caption("Cuánto cae la venta (%) por cada 1 % de alza de precio. Ej.: −0,6 → un alza de 5 % baja la venta ≈ 3 %.")
        st.dataframe({"Cuadrante": CLASSES, **{s: [DEFAULT_ELASTICITY[s][c] for c in CLASSES] for s in SCENARIOS}},
                     hide_index=True)
    ready = {s: r for s, r in results.items() if r is not None}
    if len(ready) < len(SCENARIOS):
        calculo.render_panel(classified, info, params, where="adv")
    if not ready:
        return
    st.plotly_chart(charts.scenario_compare(ready))
    rows = []
    for s in SCENARIOS:
        if s in ready:
            m = ready[s][1]
            rows.append({"Escenario": s, "Food cost hoy": pct(m["fc0"]), "Food cost logrado": pct(m["fc_new"]),
                         "Margen hoy ($)": clp(m["margin0"]), "Margen nuevo ($)": clp(m["margin_new"]),
                         "Unidades hoy": num(m["units0"]), "Unidades nuevas": num(m["units_new"]),
                         "Optimizador": "OK" if m["solver_success"] else "No convergió"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def render(classified, results: dict, params: dict, n_fusionados: int, info):
    st.title("Avanzado")
    st.markdown("#### Parámetros del optimizador")
    st.caption("Para uso técnico. Cambiar estos supuestos vuelve a correr la optimización de los tres escenarios "
               "(varios minutos, en segundo plano). Los resultados de parámetros anteriores quedan guardados.")

    with st.form("params_form"):
        maxiter = st.number_input("Iteraciones máximas del solver (maxiter)", 100, 20000, params["maxiter"], 100,
                                  help="Con ~330 platos, 300 no alcanza para converger; 3000 sí (≈2 min por escenario).")
        c1, c2, c3 = st.columns(3)
        drop = c1.slider("Caída máxima de unidades (%)", 0.0, 10.0, params["max_drop"] * 100, 0.5, format="%.1f%%",
                         help="Cuánto pueden caer las unidades totales vendidas (max_units_drop).")
        dlt = c2.slider("Rango de alza de precio (%)", 0.0, 30.0, tuple(v * 100 for v in params["bound_delta"]), 0.5, format="%.1f%%",
                        help="Límites de δ por plato (bound_delta).")
        u = c3.slider("Rango de empuje de venta (%)", -20.0, 20.0, tuple(v * 100 for v in params["bound_u"]), 0.5, format="%.1f%%",
                      help="Límites de u por plato (bound_u).")
        apply = st.form_submit_button("Recalcular con estos parámetros", type="primary")
    if apply:
        new = {"maxiter": int(maxiter), "max_drop": drop / 100,
               "bound_delta": (dlt[0] / 100, dlt[1] / 100), "bound_u": (u[0] / 100, u[1] / 100)}
        if jobs.is_running():
            ui.warn("Ya hay un cálculo en curso. Espera a que termine para lanzar otro.")
        else:
            st.session_state["params"] = new
            calculo.start(classified, info, new)  # no hace nada si esos parámetros ya estaban calculados
            st.rerun()
    if params != DEFAULT_PARAMS and st.button("Volver a los valores oficiales (Avance 3)"):
        st.session_state["params"] = dict(DEFAULT_PARAMS)
        st.rerun()

    st.markdown("---")
    _escenarios(classified, results, params, info)

    st.markdown("---")
    st.markdown("#### Calidad de los datos")
    st.write(f"- Platos duplicados fusionados automáticamente: **{n_fusionados}**.")
    m = info.meta
    if m.get("unidades_total"):
        st.write(f"- Unidades vendidas sin costo de receta (excluidas del análisis): "
                 f"**{num(m['unidades_sin_costo'])}** de {num(m['unidades_total'])} "
                 f"({pct(m['unidades_sin_costo'] / m['unidades_total'])}).")
    if m.get("excluidos"):
        with st.expander(f"Productos excluidos por no tener costo ({len(m['excluidos'])})"):
            st.dataframe(pd.DataFrame(m["excluidos"]), hide_index=True)
    if m.get("alias"):
        with st.expander(f"Productos cruzados por alias, costo aproximado ({len(m['alias'])})"):
            st.write("\n".join(f"- {a}" for a in m["alias"]))
    if not m:
        st.caption("Este archivo no tiene metadata de descarga (período, excluidos). "
                   "Las actualizaciones desde Justo la guardan automáticamente.")
