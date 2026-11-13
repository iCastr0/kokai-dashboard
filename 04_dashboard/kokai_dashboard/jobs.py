"""Cálculo de la optimización en un hilo de fondo, para no congelar la app durante varios minutos.

El estado vive a nivel de módulo (un solo proceso de Streamlit), así sobrevive a reruns y a cambios
de pestaña. Solo corre un cálculo a la vez. El hilo NO llama a la API de Streamlit."""

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import engine
from .config import DEFAULT_ELASTICITY
from kokai_menu_optimizer import run_scenario


@dataclass
class Job:
    dataset: str
    total: int
    state: str = "running"  # running | done | error
    done: int = 0
    current: str = ""
    error: str = ""
    started: float = field(default_factory=time.time)


_lock = threading.Lock()
_job: Job | None = None


def current() -> Job | None:
    return _job


def is_running() -> bool:
    return _job is not None and _job.state == "running"


def start(classified, files: dict[str, Path], params: dict, dataset_name: str) -> bool:
    """Lanza el cálculo de los escenarios que falten. False si ya hay uno corriendo."""
    global _job
    with _lock:
        if is_running():
            return False
        _job = Job(dataset=dataset_name, total=len(files))
        threading.Thread(target=_work, args=(_job, classified, files, params), daemon=True).start()
    return True


def _work(job: Job, classified, files: dict[str, Path], params: dict):
    try:
        for scen, file in files.items():
            if file.exists():
                job.done += 1
                continue
            job.current = scen
            t0 = time.time()
            out, summary = run_scenario(classified, DEFAULT_ELASTICITY[scen], params["bound_delta"],
                                        params["bound_u"], params["max_drop"], params["maxiter"])
            summary["segundos"] = round(time.time() - t0, 1)
            engine.save_result(file, out, summary)
            job.done += 1
        job.state = "done"
    except Exception as e:  # el solver nunca debe dejar el estado colgado en «running»
        job.error, job.state = f"{type(e).__name__}: {e}", "error"
