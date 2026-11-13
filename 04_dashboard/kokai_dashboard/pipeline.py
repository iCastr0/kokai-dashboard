"""Pipeline «Actualizar datos»: descarga de Justo → cruce con costos → dataset nuevo con fecha.

Reutiliza justo_fetch_sales.fetch_sales y join_ventas_costos.build_dataset (no hay subprocess),
y avisa el avance real por `on_progress(msg, frac)`.
"""

from datetime import date, timedelta
from pathlib import Path

from .config import MAESTRA_PATH
from .datasets import FUENTE_JUSTO, save_dataset


class UpdateError(Exception):
    """Falla esperable de la actualización: título corto para el usuario + detalle técnico."""

    def __init__(self, title: str, detail: str = ""):
        super().__init__(title)
        self.title, self.detail = title, detail


def run_update(desde: date, hasta: date, on_progress) -> Path:
    """Descarga las ventas entre `desde` y `hasta` (ambos incluidos) y guarda un dataset nuevo."""
    try:
        from justo_fetch_sales import JustoConfigError, fetch_sales
        import join_ventas_costos as jvc
    except ImportError as e:
        raise UpdateError("Falta una librería para actualizar", f"{e}. Instala con: pip install -r requirements.txt")

    on_progress("Paso 1 de 2 · Descargando ventas desde Justo…", 0.0)
    try:
        ventas = fetch_sales(desde.isoformat(), (hasta + timedelta(days=1)).isoformat(),
                             on_progress=lambda m, f=None: on_progress(m, None if f is None else f * 0.85))
    except JustoConfigError as e:
        raise UpdateError("Falta configurar el acceso a Justo", str(e))
    except RuntimeError as e:
        raise UpdateError("No se pudo descargar desde Justo (revisa la conexión o el token)", str(e))

    on_progress("Paso 2 de 2 · Cruzando ventas con el costo de receta…", 0.9)
    try:
        dataset, sin_costo, cero, aliased = jvc.build_dataset(ventas, MAESTRA_PATH)
    except Exception as e:
        raise UpdateError("No se pudo cruzar con la Maestra de costos", repr(e))
    if dataset.empty:
        raise UpdateError("Ningún producto vendido encontró costo en la Maestra", "")

    path = save_dataset(dataset, {
        "fuente": FUENTE_JUSTO, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "dias": (hasta - desde).days + 1, "por_local": ventas.attrs.get("por_local", {}),
        "unidades_total": float(ventas["q"].sum()), "unidades_sin_costo": float(sin_costo["q"].sum()),
        "excluidos": sin_costo[["Local", "Producto", "q"]].to_dict("records"),
        "precio_cero": int(len(cero)),
        "alias": sorted({f"{p} → costo {c:,.0f}" for p, _, _, c, _ in aliased}),
    })
    on_progress(f"Listo: {len(dataset)} filas guardadas en {path.name}", 1.0)
    return path
