"""Lo que el dashboard necesita de la Maestra de costos, además del costo por plato que ya trae el dataset:
categoría y SKU de cada plato, precios de carta por canal y el desglose de cada receta en insumos.

Las recetas viven en bloques repetidos a lo ancho y alto de cada hoja de categoría: una celda «SKU» (o
«RECETA BASE» en las hojas de bases y salsas) con el identificador al lado, una fila de encabezado
(Ingredientes/Productos, ID, UM, Valor unitario, CANT, VALOR) y debajo los ingredientes. Un ingrediente
puede ser a su vez una receta base (shari, salsas, apanados) y un combo se arma con otros platos; ambos se
expanden hasta llegar a insumos comprados."""

import warnings
from pathlib import Path

import openpyxl
import pandas as pd
import streamlit as st

from .config import MAESTRA_PATH
from join_ventas_costos import ALIASES, CATEGORY_SHEETS, load_costos, norm_name

BASE_SHEETS = ["RECETAS BASES", "RECETAS SALSAS"]
CHANNELS = {"Salón": 5, "Kokai.cl": 9, "UberEats": 13}  # columna del precio en «output Lista Precios»
_BLOCK_ROWS = 22  # filas de ingredientes bajo el encabezado de cada bloque


def _rows(wb, sheet: str) -> list[list]:
    return [list(r) for r in wb[sheet].iter_rows(values_only=True)]


def _blocks(rows: list[list], label: str):
    """(identificador, [(nombre, id, valor), ...]) por cada bloque de receta de la hoja."""
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if not (isinstance(v, str) and v.strip().upper() == label) or j + 1 >= len(row) or i + 1 >= len(rows):
                continue
            header = [str(h or "").strip().lower() for h in rows[i + 1][j:j + 6]]
            if not header or header[0] not in ("ingredientes", "productos"):
                continue
            has_id = header[1].startswith("id")
            k_val = j + (5 if has_id else 4)
            items = []
            for r in rows[i + 2:i + 2 + _BLOCK_ROWS]:
                if j >= len(r) or (isinstance(r[j], str) and r[j].strip().upper() == label):
                    break
                name, valor = r[j], r[k_val] if k_val < len(r) else None
                if isinstance(name, str) and name.strip().upper() in ("NETO", "TOTAL"):  # fila de total del bloque
                    break
                if isinstance(name, str) and name.strip() and isinstance(valor, (int, float)) and valor > 0:
                    items.append((name.strip(), r[j + 1] if has_id else None, float(valor)))
            yield row[j + 1], items


def _clean(name: str) -> str:
    """«SALMON FRESCO (KG)» → «Salmon fresco»: sin el formato de compra, en minúsculas legibles."""
    base = name.split("(")[0].strip(" -*") or name
    return base[:1].upper() + base[1:].lower()


def _explode(recipes: dict, key, memo: dict, stack=()) -> dict[str, float]:
    """{insumo: fracción del costo} de una receta, expandiendo bases y combos hasta insumos comprados."""
    if key in memo:
        return memo[key]
    shares: dict[str, float] = {}
    items = recipes.get(key)
    if not items or key in stack:
        return {}
    total = sum(v for _, _, v in items)
    for name, ref, valor in items:
        sub = _explode(recipes, ref, memo, stack + (key,)) if ref in recipes and ref != key else {}
        for ing, f in (sub or {_clean(name): 1.0}).items():
            shares[ing] = shares.get(ing, 0.0) + f * valor / total
    memo[key] = shares
    return shares


@st.cache_data(show_spinner="Leyendo la Maestra de costos…", persist="disk")  # ~20 s la primera vez
def _load(path: str, mtime_ns: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        costos = load_costos(path)
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    # Recetas: platos por SKU; bases por su ID de ingrediente (así las referencian los platos).
    recipes: dict = {}
    for sheet in CATEGORY_SHEETS:
        if sheet in wb.sheetnames:
            for sku, items in _blocks(_rows(wb, sheet), "SKU"):
                if isinstance(sku, (int, float)) and items:
                    recipes[("sku", int(sku))] = items
    for sheet in BASE_SHEETS:
        rows = _rows(wb, sheet)
        base_id = {str(r[0]).strip(): int(r[1]) for r in rows[1:] if r[0] and isinstance(r[1], (int, float))}
        for name, items in _blocks(rows, "RECETA BASE"):
            if items and str(name).strip() in base_id:
                recipes[("id", base_id[str(name).strip()])] = items
    sku_by_norm = dict(zip(costos["norm"], costos["SKU"].astype(int)))
    # Referencias de cada ingrediente: por ID (insumo o base) o, en los combos, por nombre de plato.
    for key, items in recipes.items():
        recipes[key] = [(n, ("id", int(i)) if isinstance(i, (int, float))
                         else ("sku", sku_by_norm[norm_name(n)]) if norm_name(n) in sku_by_norm else None, v)
                        for n, i, v in items]
    memo: dict = {}
    insumos = pd.DataFrame(
        [(sku, ing, f) for (kind, sku) in list(recipes) if kind == "sku"
         for ing, f in _explode(recipes, ("sku", sku), memo).items()],
        columns=["SKU", "Insumo", "fraccion"])

    # Precios de carta por canal (con IVA). «No disponible» no borra el precio: solo se informa.
    lista = _rows(wb, "output Lista Precios")
    precios = pd.DataFrame(
        [{"SKU": int(r[0]), **{ch: (round(r[col]) if isinstance(r[col], (int, float)) and r[col] > 0 else None)
                               for ch, col in CHANNELS.items()}}
         for r in lista[1:] if isinstance(r[0], (int, float))])
    catalogo = costos.drop_duplicates("norm")[["norm", "SKU", "Producto", "Categoria"]].copy()
    catalogo["SKU"] = catalogo["SKU"].astype(int)
    return catalogo, precios, insumos


def load(path: Path = MAESTRA_PATH):
    """(catálogo norm→SKU/Categoria, precios por canal por SKU, fracción de costo por insumo por SKU)."""
    return _load(str(path), path.stat().st_mtime_ns)


def match_sku(producto: str, catalogo: pd.DataFrame) -> tuple[int | None, str | None]:
    """SKU y categoría de un plato del dataset (nombre de Justo), con los mismos alias que el cruce de costos."""
    by_norm = catalogo.set_index("norm")
    key = norm_name(producto)
    for k in [key] + ALIASES.get(key, []):
        if k in by_norm.index:
            row = by_norm.loc[k]
            return int(row["SKU"]), row["Categoria"]
    return None, None


@st.cache_data(show_spinner=False, persist="disk")
def _fechas(path: str, mtime_ns: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = list(wb["Ingredientes"].iter_rows(values_only=True))
    col = [str(h or "").strip().lower() for h in rows[0]].index("fecha actualización")
    f = [r[col] for r in rows[1:] if hasattr(r[col], "year")]
    return (min(f).date(), max(f).date()) if f else (None, None)


def fechas_precios(path: Path = MAESTRA_PATH):
    """(fecha más antigua, más reciente) de actualización de precios de insumos en la Maestra."""
    return _fechas(str(path), path.stat().st_mtime_ns)
