"""Estilo de tablas con nombres de negocio (nada de delta_precio / u_mezcla en la UI)."""

import pandas as pd

from .config import CLASS_COLOR, CLASS_LABEL, CLASS_TEXT

_BY_LABEL = {CLASS_LABEL[k]: k for k in CLASS_COLOR}


def style_class(t: pd.DataFrame, col: str = "Cuadrante"):
    """Pinta la columna del cuadrante con los colores del mapa del menú."""
    def paint(v):
        k = _BY_LABEL.get(v, v)
        return f"background-color: {CLASS_COLOR[k]}; color: {CLASS_TEXT[k]}; font-weight: 600" if k in CLASS_COLOR else ""
    styler = t.style
    return (styler.map if hasattr(styler, "map") else styler.applymap)(paint, subset=[col])
