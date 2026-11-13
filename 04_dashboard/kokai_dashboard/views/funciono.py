"""5 · Cómo saber si funcionó: 4 indicadores mensuales contra la línea base, con meta y semáforo."""

import streamlit as st

from .. import datasets, seguimiento, ui
from ..config import BASELINE_DATASET, JUSTO_PASOS, MIN_UNIDADES_PLATO, SEM_TICKET, SEM_UNIDADES, SEM_VENTA
from ..fmt import clp, num, pct
from .parte2 import PARTE


def _p(x: float) -> str:
    return num(abs(x) * 100, 0) + " %"


def _textos(fc_objetivo: float, base_mes: str) -> dict:
    """Nombre, qué mide, meta, regla del semáforo y de dónde sale, para cada indicador."""
    return {
        "fc": dict(
            nombre="Food cost", mide="Costo de insumos según receta ÷ venta neta de IVA, todos los locales.",
            meta=f"≤ {pct(fc_objetivo)}", fmt=pct,
            regla=f"Verde: llega a la meta (±0,3 pts). Amarillo: bajó desde {base_mes} pero no llega. "
                  f"**Rojo: igual o peor que {base_mes} → revisar qué insumo subió (ver «Reglas») y las porciones de "
                  f"los platos que más gastan.**",
            pasos=["No sale directo de Justo: se calcula aquí con las ventas por producto y las recetas.",
                   *JUSTO_PASOS["dashboard"]], alt=JUSTO_PASOS["ventas_producto"]),
        "unidades": dict(
            nombre="Unidades de los platos con alza", fmt=lambda x: num(x, 1) + " al día",
            mide="Unidades vendidas por día de los platos a los que el plan les subió el precio.",
            meta=f"no caer más de {_p(SEM_UNIDADES[1])}",
            regla=f"Verde: caen menos de {_p(SEM_UNIDADES[0])}. Amarillo: entre {_p(SEM_UNIDADES[0])} y "
                  f"{_p(SEM_UNIDADES[1])}. **Rojo: caen más de {_p(SEM_UNIDADES[1])} → revertir el alza en los "
                  f"platos que más cayeron (lista abajo).**",
            pasos=JUSTO_PASOS["dashboard"], alt=JUSTO_PASOS["ventas_producto"]),
        "ticket": dict(
            nombre="Ticket promedio", fmt=clp, mide="Venta con IVA ÷ número de pedidos, todos los locales.",
            meta=f"≥ {base_mes}",
            regla=f"Verde: igual o mayor que {base_mes}. Amarillo: hasta {_p(SEM_TICKET[1])} menos. **Rojo: baja más "
                  f"de {_p(SEM_TICKET[1])} → los clientes gastan menos por pedido: no subir más precios y revisar las "
                  f"alzas en tablas y estrellas.**",
            pasos=JUSTO_PASOS["ticket"], alt=None),
        "venta": dict(
            nombre="Venta total", fmt=lambda x: clp(round(x, -3)) + " al día",
            mide="Venta neta de IVA por día (los meses no tienen el mismo largo).",
            meta=f"no caer más de {_p(SEM_VENTA[0])}",
            regla=f"Verde: cae menos de {_p(SEM_VENTA[0])}. Amarillo: entre {_p(SEM_VENTA[0])} y {_p(SEM_VENTA[1])}. "
                  f"**Rojo: cae más de {_p(SEM_VENTA[1])} → compararlo con el mismo mes del año anterior antes de "
                  f"culpar al plan; si la caída está en los platos con alza, revertirlas.**",
            pasos=JUSTO_PASOS["dashboard"], alt=JUSTO_PASOS["ventas_producto"][:3]),
    }


def _cambio(i: dict) -> str:
    if i["clave"] == "fc":
        return f"{'+' if i['cambio_pts'] > 0 else ''}{num(i['cambio_pts'], 1)} pts"
    if i.get("cambio") is None:
        return ""
    return f"{'+' if i['cambio'] > 0 else '−' if i['cambio'] < 0 else ''}{_p(i['cambio'])}"


def _tarjeta(col, i: dict, t: dict, base_mes: str, hay_mes: bool):
    with col:
        valor = t["fmt"](i["valor"]) if hay_mes and i["valor"] is not None else "—"
        base = t["fmt"](i["base"]) if i["base"] is not None else "sin dato"
        cambio = f" · {_cambio(i)} vs. {base_mes}" if hay_mes and _cambio(i) else ""
        st.markdown(
            f"<div class='ind'><div class='t'><b>{t['nombre']}</b>{ui.semaforo(i['estado']) if hay_mes else ''}</div>"
            f"<div class='v'>{valor}</div><div class='s'>{base_mes}: {base}{cambio} · meta: {t['meta']}</div>"
            f"<div class='s'>{t['mide']}</div></div>", unsafe_allow_html=True)
        st.markdown(t["regla"])
        with st.expander("Dónde se saca en Justo, paso a paso"):
            st.markdown("\n".join(f"{n}. {x}" for n, x in enumerate(t["pasos"], 1)))
            if t["alt"]:
                st.markdown("**Sin el dashboard (directo en el panel de Justo):**\n"
                            + "\n".join(f"{n}. {x}" for n, x in enumerate(t["alt"], 1)))
            st.caption("Los nombres exactos de los menús de Justo hay que confirmarlos con quien lo administra en Kokai.")


def _ticket_manual(mes, etiqueta: str, key: str):
    actual = mes.ticket()
    v = st.number_input(f"Ticket promedio de {etiqueta} ($, con IVA)", 0, 200_000, int(actual or 0), 100, key=key,
                        help="Sale del reporte de ventas de Justo: venta total ÷ número de pedidos.")
    if v != int(actual or 0):
        seguimiento.guardar_ticket(mes.info, v or None)
        st.rerun()


def render(ctx):
    ui.page_header(PARTE, "Cómo saber si funcionó", ctx.info,
                   "Cuatro indicadores para revisar una vez al mes, comparando contra el mes con el que se armó el plan.")
    base, plan, totals = seguimiento.linea_base()
    base_mes = base.info.mes
    if plan is None:
        ui.note(f"Falta calcular el plan con los datos de {base_mes} (página «Plan de acción»).")
        return

    otros = [i for i in datasets.list_datasets() if i.path != BASELINE_DATASET]
    if otros:
        sel = st.selectbox("Mes a revisar", otros, format_func=lambda i: f"{i.mes} · {i.fuente} ({i.label})",
                           key="seg_mes")
        mes = seguimiento.cargar(sel)
    else:
        ui.note(f"**Todavía no hay un mes para comparar contra {base_mes}.** Cuando termine el primer mes con "
                "el plan aplicado, cárgalo con **Actualizar desde Justo** («Un mes completo») o **Subir un Excel "
                "manual** en la barra lateral, y vuelve a esta página. Mientras tanto se muestra la línea base.")
        mes = base
    hay_mes = mes is not base
    if hay_mes and not mes.info.dias:
        ui.warn("Ese archivo no informa su período: se asumió un mes de 30 días para comparar por día.")

    ind = seguimiento.indicadores(base, mes, plan, totals, ctx.fc_meta)
    tx = _textos(ind[0]["objetivo"], base_mes)
    for fila in (ind[:2], ind[2:]):
        cols = st.columns(2, gap="medium")
        for col, i in zip(cols, fila):
            _tarjeta(col, i, tx[i["clave"]], base_mes, hay_mes)

    if base.ticket() is None or (hay_mes and mes.ticket() is None):
        st.markdown("##### Ticket promedio a mano")
        st.caption("Las descargas desde Justo traen el número de pedidos y el ticket se calcula solo. Para los "
                   "meses que no lo traen, ingrésalo aquí (queda guardado).")
        c1, c2 = st.columns(2)
        with c1:
            if base.ticket() is None:
                _ticket_manual(base, base_mes, "tk_base")
        with c2:
            if hay_mes and mes.ticket() is None:
                _ticket_manual(mes, mes.info.mes, "tk_mes")

    if not hay_mes:
        return
    st.markdown("---")
    st.markdown("#### Platos con alza: qué pasó con sus unidades")
    tot, det = seguimiento.unidades_ajustados(base, mes, plan)
    st.dataframe(tot.assign(
        Estado=[ui.semaforo_txt(e) for e in tot["estado"]],
        **{"Cambio": tot["cambio"] * 100})[["Cuadrante", "platos", "dia_base", "dia_mes", "Cambio", "Estado"]],
        hide_index=True, column_config={
            "platos": st.column_config.NumberColumn("Platos (× local)"),
            "dia_base": st.column_config.NumberColumn(f"Unid./día {base_mes}", format="%.1f"),
            "dia_mes": st.column_config.NumberColumn(f"Unid./día {mes.info.mes}", format="%.1f"),
            "Cambio": st.column_config.NumberColumn(format="%+.1f%%")})
    rojos = det[det["estado"] == "rojo"]
    st.markdown(f"**Platos donde conviene revertir el alza** (cayeron más de {_p(SEM_UNIDADES[1])}; solo platos "
                f"con al menos {MIN_UNIDADES_PLATO} unidades en {base_mes}): {len(rojos)}")
    if len(rojos):
        st.dataframe(rojos.assign(Cambio=rojos["cambio"] * 100, Alza=rojos["alza"] * 100)[
            ["Plato", "Local", "Cuadrante", "Alza", "dia_base", "dia_mes", "Cambio"]], hide_index=True,
            column_config={"Alza": st.column_config.NumberColumn("Alza aplicada", format="%.0f%%"),
                           "dia_base": st.column_config.NumberColumn(f"Unid./día {base_mes}", format="%.2f"),
                           "dia_mes": st.column_config.NumberColumn(f"Unid./día {mes.info.mes}", format="%.2f"),
                           "Cambio": st.column_config.NumberColumn(format="%+.0f%%")})
    st.caption("Ojo con la estacionalidad: feriados, vacaciones y clima mueven la venta sin que el plan tenga que "
               "ver. Si un indicador sale rojo, compáralo también con el mismo mes del año anterior.")
