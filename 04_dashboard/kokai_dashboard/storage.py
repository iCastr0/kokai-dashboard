"""Persistencia en la nube: espeja los datos del proyecto en un repositorio *dataset* privado de Hugging Face.

El disco de un Space gratis se borra en cada reinicio. Para no perder las descargas de Justo, las cargas
manuales, los tickets ingresados a mano ni los resultados del optimizador:

- Al arrancar el proceso se baja el repositorio completo sobre la carpeta del proyecto (`sync_down`).
  Ahí viven también la Maestra y el entregable de octubre, así el código del Space no lleva datos de Kokai.
- Cada archivo nuevo o modificado se sube en segundo plano (`push`), sin frenar la app.

Solo se activa si existen las variables HF_DATA_REPO (ej. «usuario/kokai-datos») y HF_TOKEN (con permiso de
escritura). En local, sin esas variables, todo esto no hace nada y la app funciona igual que antes.
Las rutas dentro del repositorio son las mismas que en el proyecto (relativas a kokai_capstone/).
"""

import logging
import os
import threading
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)


def _repo() -> str:  # se lee al usarse (no al importar): app.py copia los Secrets de Streamlit al entorno
    return os.environ.get("HF_DATA_REPO", "").strip()


def _token() -> str | None:
    return os.environ.get("HF_TOKEN", "").strip() or None


_lock = threading.Lock()
_status = {"down": None, "errors": []}  # para mostrar en «Avanzado» si algo falló


def enabled() -> bool:
    return bool(_repo())


def status() -> dict:
    return dict(_status, repo=_repo())


def sync_down():
    """Baja todo el repositorio de datos sobre ROOT. Se llama una vez por proceso (ver app.py)."""
    if not enabled():
        return
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(_repo(), repo_type="dataset", local_dir=ROOT, token=_token())
        _status["down"] = "ok"
    except Exception as e:  # sin red o sin permiso: la app sigue con lo que haya en disco
        _status["down"] = repr(e)
        log.exception("No se pudo bajar %s", _repo())


def push(*paths: Path):
    """Sube estos archivos al repositorio de datos en segundo plano (un commit por llamada)."""
    if not enabled():
        return
    paths = [Path(p) for p in paths if p and Path(p).exists()]
    if paths:
        threading.Thread(target=_upload, args=(paths,), daemon=True).start()


def _upload(paths: list[Path]):
    from huggingface_hub import CommitOperationAdd, HfApi
    ops = [CommitOperationAdd(path_in_repo=p.resolve().relative_to(ROOT).as_posix(), path_or_fileobj=str(p))
           for p in paths]
    try:
        with _lock:  # commits en serie: evita conflictos entre subidas simultáneas
            HfApi(token=_token()).create_commit(_repo(), ops, repo_type="dataset",
                                              commit_message=f"dashboard: {', '.join(p.name for p in paths)}")
    except Exception as e:
        _status["errors"].append(f"{', '.join(p.name for p in paths)}: {e!r}")
        log.exception("No se pudo subir %s", paths)
