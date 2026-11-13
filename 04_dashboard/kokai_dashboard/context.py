"""Lo que comparten todas las páginas: dataset activo, clasificación, resultados del optimizador y los
números de negocio derivados (cacheados: cambiar de página no recalcula nada)."""

from dataclasses import dataclass
from functools import cached_property

import pandas as pd
import streamlit as st

from . import analisis
from .config import RANGE_MID


@st.cache_data(show_spinner=False)
def _enrich(classified: pd.DataFrame) -> pd.DataFrame:
    return analisis.enrich(classified)


@st.cache_data(show_spinner=False)
def _plan(out_base: pd.DataFrame, enriched: pd.DataFrame, _info, info_key: str):
    return analisis.build_plan(out_base, enriched, _info)


@dataclass
class Ctx:
    info: object
    classified: pd.DataFrame
    results: dict  # {escenario: (out, summary) | None}
    params: dict
    fc_meta: float | None  # meta de food cost (mismo método que el calculado); None = por definir

    @cached_property
    def enriched(self) -> pd.DataFrame:
        return _enrich(self.classified)

    @cached_property
    def insumos(self) -> pd.DataFrame:
        return analisis.gasto_insumos(self.enriched)

    @property
    def has_plan(self) -> bool:
        return self.results.get(RANGE_MID) is not None

    @cached_property
    def plan(self) -> pd.DataFrame:
        return self._plan_totals[0]

    @cached_property
    def totals(self) -> dict:
        return self._plan_totals[1]

    @cached_property
    def _plan_totals(self):
        out, _ = self.results[RANGE_MID]
        return _plan(out, self.enriched, self.info, f"{self.info.path}|{self.info.dias}")
