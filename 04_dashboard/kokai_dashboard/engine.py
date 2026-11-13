"""Clasificación cacheada + almacenamiento en disco de los resultados de la optimización.

La optimización con datos reales tarda varios minutos, así que no vive en st.cache_data: cada escenario
se guarda en data/cache/ con una clave (contenido del dataset + escenario + parámetros). Reabrir la app
o volver a un dataset anterior muestra los resultados al instante. El cálculo corre en jobs.py."""

import hashlib
import json
import pickle
from pathlib import Path

import pandas as pd
import streamlit as st

from . import storage
from .config import DATA_DIR, DEFAULT_ELASTICITY, SCENARIOS
from kokai_menu_optimizer import classify, dedupe_items, load_items

CACHE_DIR = DATA_DIR / "cache"
# Sube cuando cambia el modelo (no los datos): invalida los resultados guardados con la versión anterior.
# 2 = margen y food cost con precio neto de IVA (12-nov-2026).
MODEL_VERSION = 2


@st.cache_data(show_spinner=False)
def _prepare(path: str, mtime_ns: int) -> tuple[pd.DataFrame, int]:
    # mtime_ns forma parte de la clave: si el archivo cambia, se recalcula.
    raw = load_items(path)
    clean = dedupe_items(raw, verbose=False)
    return classify(clean), len(raw) - len(clean)


def get_classified(path: Path) -> tuple[pd.DataFrame, int]:
    """(tabla clasificada, platos fusionados por duplicado). Solo se recalcula si cambia el archivo."""
    return _prepare(str(path), path.stat().st_mtime_ns)


@st.cache_data(show_spinner=False)
def _digest(path: str, mtime_ns: int) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def result_files(path: Path, params: dict) -> dict[str, Path]:
    """{escenario: archivo donde vive (o vivirá) su resultado} para este dataset y estos parámetros."""
    digest = _digest(str(path), path.stat().st_mtime_ns)
    files = {}
    for scen in SCENARIOS:
        raw = json.dumps([MODEL_VERSION, digest, scen, DEFAULT_ELASTICITY[scen], params["bound_delta"], params["bound_u"],
                          params["max_drop"], params["maxiter"]], sort_keys=True)
        files[scen] = CACHE_DIR / f"{hashlib.sha1(raw.encode()).hexdigest()[:20]}.pkl"
    return files


def save_result(file: Path, out: pd.DataFrame, summary: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps((out, summary)))
    tmp.replace(file)  # escritura atómica: nunca queda un pickle a medias
    storage.push(file)


def load_results(path: Path, params: dict) -> dict:
    """{escenario: (out_df, summary) | None}. None = todavía no calculado."""
    results = {}
    for scen, f in result_files(path, params).items():
        try:
            results[scen] = pickle.loads(f.read_bytes()) if f.exists() else None
        except Exception:  # cache corrupto o de otra versión: se trata como no calculado
            results[scen] = None
    return results
