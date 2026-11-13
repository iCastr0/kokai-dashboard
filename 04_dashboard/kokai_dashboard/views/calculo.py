"""Panel «Calcular recomendaciones»: botón + progreso del cálculo en segundo plano."""

import time

import streamlit as st

from .. import engine, jobs, ui


def start(classified, info, params) -> bool:
    files = engine.result_files(info.path, params)
    if all(f.exists() for f in files.values()):
        return False
    return jobs.start(classified, files, params, info.path.name)


@st.fragment(run_every=3)
def _progress():
    job = jobs.current()
    if job is None or job.state != "running":
        st.rerun()  # rerun completo: carga los resultados o muestra el error
        return
    m, s = divmod(int(time.time() - job.started), 60)
    st.progress(job.done / job.total,
                text=f"Calculando escenario «{job.current}» ({job.done + 1} de {job.total}) · {m} min {s:02d} s")


def render_panel(classified, info, params, where: str):
    job = jobs.current()
    if jobs.is_running():
        ui.note("Las recomendaciones se están calculando en segundo plano. Puedes seguir usando las otras "
                "pestañas; esta se actualiza sola.")
        if job.dataset != info.path.name:
            st.caption(f"(El cálculo en curso es del dataset {job.dataset}; espera a que termine para lanzar este.)")
        _progress()
        return
    if job is not None and job.state == "error":
        ui.error(f"El cálculo falló: {job.error}")
    ui.note("Las recomendaciones **todavía no están calculadas** para estos datos y parámetros. Con los datos "
            "completos el optimizador tarda varios minutos por escenario; se guarda el resultado y "
            "después se abre al instante.")
    if st.button("Calcular recomendaciones", type="primary", key=f"calc_{where}"):
        start(classified, info, params)
        st.rerun()
