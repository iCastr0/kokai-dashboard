"""Dashboard Kokai · menu engineering y food cost.  Ejecutar:  streamlit run app.py"""

import hmac
import os
from datetime import date, timedelta

import streamlit as st

from kokai_dashboard import config, datasets, engine, storage, ui
from kokai_dashboard.context import Ctx
from kokai_dashboard.pipeline import UpdateError, run_update
from kokai_dashboard.views import (avanzado, calculo, funciono, mapa, parte2, plan, plata, reglas, resumen,
                                   supuestos)

st.set_page_config(page_title="Kokai · Menu engineering", layout="wide")
ui.apply()

ss = st.session_state

# --- Contraseña (solo si existe APP_PASSWORD, ej. en los Secrets del Space; en local no se pide) --------
if (_pwd := os.environ.get("APP_PASSWORD")) and not ss.get("auth_ok"):
    st.markdown("<div class='brand'>KOKAI</div>", unsafe_allow_html=True)
    with st.form("login"):
        intento = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if hmac.compare_digest(intento.encode(), _pwd.encode()):
                ss["auth_ok"] = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    st.stop()


@st.cache_resource(show_spinner="Cargando datos guardados…")
def _sync_inicial():
    """Una vez por proceso: baja los datos guardados en la nube (no hace nada sin HF_DATA_REPO)."""
    storage.sync_down()
    return True


_sync_inicial()
ss.setdefault("params", dict(config.DEFAULT_PARAMS))
ss.setdefault("update_days", 30)
ss.setdefault("fc_meta", None if config.FC_META is None else config.FC_META * 100)

# --- Dataset activo -----------------------------------------------------------------------------
infos = datasets.list_datasets()
by_path = {str(i.path): i for i in infos}
if "pending_dataset" in ss:  # se aplica antes de crear el selector (Streamlit no permite cambiarlo después)
    ss["dataset_sel"] = ss.pop("pending_dataset")
if ss.get("dataset_sel") not in by_path:
    first = datasets.default_dataset(infos)
    ss["dataset_sel"] = str(first.path) if first else None
if msg := ss.pop("toast", None):
    st.toast(msg)

with st.sidebar:
    st.markdown("<div class='brand'>KOKAI</div>", unsafe_allow_html=True)
    st.markdown("#### Datos")
    if storage.enabled():
        _st = storage.status()
        if _st["down"] != "ok" or _st["errors"]:
            with st.expander("⚠️ Problema guardando en la nube"):
                st.caption("Los datos nuevos podrían perderse si la app se reinicia.")
                st.code("\n".join(([f"Bajada: {_st['down']}"] if _st["down"] != "ok" else []) + _st["errors"][-3:]),
                        language=None)
    if infos:
        st.selectbox("Dataset activo", list(by_path), key="dataset_sel",
                     format_func=lambda p: by_path[p].label,
                     help="Puedes volver a una descarga anterior sin llamar de nuevo a la API.")
    with st.expander("Meta de food cost"):
        st.number_input("Meta (%)", 5.0, 60.0, key="fc_meta", step=0.1, format="%.1f", placeholder="por definir",
                        help="En el mismo método que el food cost calculado (costo de receta ÷ venta neta).")
    with st.expander("Actualizar desde Justo"):
        st.caption("Descarga las ventas reales de los 3 locales y las cruza con el costo de receta. "
                   "Puede tardar un par de minutos.")
        modo = st.radio("Período", ["Un mes completo", "Últimos N días"], key="update_mode",
                        help="Para revisar el plan mes a mes conviene descargar meses completos.")
        if modo == "Un mes completo":
            ini = st.selectbox("Mes", datasets.ultimos_meses(), key="update_month", format_func=datasets.nombre_mes)
            rango = datasets.rango_mes(ini)
        else:
            st.number_input("Últimos N días", 1, 365, key="update_days")
            rango = (date.today() - timedelta(days=int(ss["update_days"])), date.today())
        if st.button("Actualizar datos", type="primary"):
            ss["_run_update"] = rango
    with st.expander("Subir un Excel manual"):
        st.caption("Columnas: Local, Producto, q (unidades), p (precio con IVA). Si no trae c (costo de "
                   "receta), se cruza solo con la Maestra.")
        up = st.file_uploader("Archivo .xlsx o .csv", type=["xlsx", "xls", "csv"], key="uploader")
        mes_up = st.selectbox("Mes de las ventas", [None] + datasets.ultimos_meses(), key="upload_month",
                              format_func=lambda d: "No informado" if d is None else datasets.nombre_mes(d))
        if up is not None and st.button("Usar este archivo"):
            df_up, err = datasets.read_upload(up)
            if err:
                ui.error(err)
            else:
                meta = {"fuente": "Carga manual", "archivo_original": up.name}
                if mes_up is not None:
                    d0, d1 = datasets.rango_mes(mes_up)
                    meta |= {"desde": d0.isoformat(), "hasta": d1.isoformat(), "dias": (d1 - d0).days + 1}
                p = datasets.save_dataset(df_up, meta, "carga_manual")
                ss["pending_dataset"] = str(p)
                ss["autocalc"] = True
                ss["toast"] = f"Archivo cargado: {len(df_up)} filas."
                st.rerun()

# --- Actualización bajo demanda (no corre al abrir la página) ---------------------------------------
if rango_update := ss.pop("_run_update", None):
    with st.status("Actualizando datos…", expanded=True) as status:
        bar, log, lines = st.progress(0.0), st.empty(), []

        def on_progress(msg, frac=None):
            lines.append(msg.rstrip())
            log.code("\n".join(lines[-6:]), language=None)
            if frac is not None:
                bar.progress(min(max(float(frac), 0.0), 1.0))

        try:
            new_path = run_update(*rango_update, on_progress)
        except UpdateError as e:
            status.update(label=f"No se pudo actualizar: {e.title}", state="error")
            ui.error(f"**{e.title}.** Se sigue mostrando el último dataset cargado.")
            if e.detail:
                st.code(e.detail, language=None)
        except Exception as e:
            status.update(label="Error inesperado al actualizar", state="error")
            ui.error("Error inesperado. Se sigue mostrando el último dataset cargado.")
            st.code(repr(e), language=None)
        else:
            status.update(label="Datos actualizados", state="complete")
            ss["pending_dataset"] = str(new_path)
            ss["autocalc"] = True
            ss["toast"] = "Datos actualizados desde Justo."
            st.rerun()

# --- Datos para todas las páginas --------------------------------------------------------------------
if not infos or not ss.get("dataset_sel"):
    st.title("Menu engineering y food cost")
    ui.note("Todavía no hay datos. Usa **Actualizar desde Justo** o **Subir un Excel manual** en la barra lateral.")
    st.stop()

info = by_path[ss["dataset_sel"]]
try:
    classified, n_fus = engine.get_classified(info.path)
except ValueError as e:
    ui.error(f"El dataset activo no se pudo usar: {e}")
    st.stop()
except Exception as e:
    ui.error("No se pudo leer el dataset activo. Prueba con otro desde la barra lateral.")
    st.code(repr(e), language=None)
    st.stop()

params = ss["params"]
if ss.pop("autocalc", False):  # dataset recién actualizado/subido: calcular en segundo plano
    calculo.start(classified, info, params)
results = engine.load_results(info.path, params)  # {escenario: (out, summary) | None si falta calcular}
for scen, r in results.items():
    if r is not None and not r[1]["solver_success"]:
        ui.warn(f"Escenario «{scen}»: el optimizador no convergió del todo ({r[1]['solver_message']}). "
                "Sus números pueden no ser confiables.")
if info.meta.get("unidades_total") and info.meta["unidades_sin_costo"] / info.meta["unidades_total"] > 0.10:
    ui.warn("Más del 10 % de las unidades vendidas no tienen costo de receta y quedaron fuera. "
            "Revisa «Avanzado».")
if params != config.DEFAULT_PARAMS:
    ui.note("Estás viendo resultados con **parámetros avanzados modificados** (página «Avanzado»).")

ctx = Ctx(info, classified, results, params, None if ss["fc_meta"] is None else ss["fc_meta"] / 100)


# --- Navegación: dos partes, cada una con sus secciones -----------------------------------------------
def _page(fn, title: str, slug: str, default: bool = False):
    return st.Page(fn, title=title, url_path=slug, default=default)


pg = st.navigation({
    resumen.PARTE: [
        _page(lambda: resumen.render(ctx), "Resumen", "resumen", default=True),
        _page(lambda: plata.render(ctx), "Dónde se va la plata", "donde-se-va-la-plata"),
        _page(lambda: mapa.render(ctx), "Mapa del menú", "mapa-del-menu"),
        _page(lambda: plan.render(ctx), "Plan de acción", "plan-de-accion"),
    ],
    parte2.PARTE: [
        _page(lambda: funciono.render(ctx), "Cómo saber si funcionó", "como-saber-si-funciono"),
        _page(lambda: reglas.render(ctx), "Reglas para decisiones futuras", "reglas-para-decisiones"),
        _page(lambda: supuestos.render(ctx), "Supuestos y vigencia", "supuestos-y-vigencia"),
    ],
    "Técnico": [
        _page(lambda: avanzado.render(classified, results, params, n_fus, info), "Avanzado", "avanzado"),
    ],
})
pg.run()
