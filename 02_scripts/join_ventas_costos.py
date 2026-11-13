#!/usr/bin/env python3
"""
join_ventas_costos.py
======================

Cruza las ventas reales descargadas de Justo (Local, Producto, q, p) con el
costo real por receta de la Maestra de costos (columna "Costo neto" en cada
hoja de categoría: SASHIMI, GUNKAN, NIGIRI, etc.) para armar el input final
que espera `kokai_menu_optimizer.py` (v2): Local, Producto, q, p, c.

El cruce se hace por nombre de plato normalizado (sin tildes, mayúsculas,
sufijos entre paréntesis), porque el nombre no calza exacto entre Justo
(el POS) y la Maestra de costos (la hoja de recetas).

USO
---
    python3 join_ventas_costos.py \\
        --ventas ventas_justo.xlsx \\
        --maestra ../01_datos_originales/MAESTRA_KOKAI_COSTOS_PRODUCCION_Abr2026_v5.xlsx \\
        --output ventas_con_costo.xlsx

Esto escribe:
- `ventas_con_costo.xlsx`: Local, Producto, q, p, c — listo para
  kokai_menu_optimizer.py.
- Imprime en pantalla qué productos de las ventas NO encontraron costo
  (hay que revisarlos a mano: ¿combo/promo nuevo? ¿nombre raro en Justo?)
  y qué platos de la Maestra no aparecieron en las ventas (normal — no
  todo el menú se vende todos los meses).
"""

import argparse
import re
import sys

import pandas as pd

CATEGORY_SHEETS = [
    "GUNKAN", "COMBINACIONES", "TIRADITOS", "SASHIMI", "CESHIMI", "NIGIRI", "CEVICHES",
    "HOSOMAKI", "CALIFORNIA ROLLS", "SPECIALS ROLLS", "CHEESE ROLLS ",
    "VEGGIE ROLLS ", "TEMPURA ROLLS ", "ORIENTAL ROLLS", "KETO ROLLS",
    "VEGAN ROLLS", "NIKKEI ROLLS", "ACEVICHADOS", "GOHAN", "PIQUEOS",
    "EXTRAS", "MOCKTAIL", "VINOS Y TRAGOS", "POSTRES", "BEBIDAS",
]


# Nombres que Justo usa de forma distinta a la Maestra de costos (plural/
# singular, variantes de un roll que Justo no distingue, "Coca Cola" vs
# "Cocacola" sin espacio). Cuando una clave mapea a más de un nombre de la
# Maestra, se usa el COSTO PROMEDIO de esas variantes (son platos parecidos
# con costos cercanos) y se marca con un aviso — no es exacto, es la mejor
# aproximación posible sin que Justo distinga la variante vendida.
ALIASES = {
    "california sake": ["california sake sesamo", "california sake ciboulette"],
    "california ebi": ["california ebi sesamo", "california ebi ciboulette"],
    "california tori": ["california tori sesamo", "california tori ciboulette"],
    "california spicy tuna": ["spicy tuna sesamo"],
    "gyozas de verduras": ["gyoza de verduras"],
    "empanadas de camaron queso": ["empanada de camaron queso"],
    "empanadas champinon queso": ["empanada de champinon queso"],
    "coca cola": ["cocacola"],
    "coca cola zero": ["cocacola zero"],
    # "Dúo Premium" (como lo llama Justo/la web kokai.cl) es el mismo combo
    # que la Maestra registra como "Acevichado + parrillero" (SKU 271,
    # Camarón Acevichado 9pz + Parrillero 9pz = 18 piezas) — confirmado
    # contra la descripción pública en kokai.cl/pedir.
    "duo premium": ["acevichado parrillero"],
}


def norm_name(s) -> str:
    """Normaliza un nombre de plato para poder cruzarlo entre sistemas:
    sin tildes, minúsculas, sin sufijos entre paréntesis, sin espacios extra."""
    import unicodedata
    s = str(s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", "", s)          # quita "(tartar de atun)", etc.
    s = re.sub(r"[^a-z0-9 ]", " ", s)      # quita puntuación
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_costos(maestra_path: str) -> pd.DataFrame:
    """Lee todas las hojas de categoría y arma una tabla SKU, Producto, Categoria, c."""
    rows = []
    for sheet in CATEGORY_SHEETS:
        try:
            df = pd.read_excel(maestra_path, sheet_name=sheet, header=0, usecols=[0, 1, 2, 3, 4])
        except ValueError:
            print(f"  (aviso: no encontré la hoja '{sheet}' en la maestra, la salto)")
            continue
        df.columns = ["SKU", "Producto", "Costo", "Merma", "Costo neto"]
        df = df.dropna(subset=["SKU", "Producto"])
        df = df[df["Producto"].astype(str).str.strip().str.lower() != "agregar sku"]
        df["Categoria"] = sheet.strip()
        rows.append(df[["SKU", "Producto", "Categoria", "Costo neto"]])
    costos = pd.concat(rows, ignore_index=True)
    costos = costos.rename(columns={"Costo neto": "c"})
    costos["norm"] = costos["Producto"].apply(norm_name)
    return costos


def prepare_ventas(df: pd.DataFrame):
    """Valida columnas, separa las filas con precio $0 y agrega `norm`.
    Devuelve (ventas_limpias, filas_precio_cero). Lanza ValueError si faltan columnas."""
    needed = {"Local", "Producto", "q", "p"}
    if not needed.issubset(df.columns):
        raise ValueError(f"El archivo de ventas debe tener columnas {needed}, tiene {set(df.columns)}")
    cero = df[df["p"] <= 0]
    df = df[df["p"] > 0].copy()
    df["norm"] = df["Producto"].apply(norm_name)
    return df, cero


def load_ventas(ventas_path: str) -> pd.DataFrame:
    try:
        df, cero = prepare_ventas(pd.read_excel(ventas_path))
    except ValueError as e:
        sys.exit(str(e))
    if not cero.empty:
        print(f"\nAviso: {len(cero)} fila(s) con precio $0 — probablemente modificadores/extras "
              f"que vinieron como línea de producto aparte, no un plato vendido de verdad. "
              f"Se excluyen del cruce:")
        print(cero[["Local", "Producto", "q", "p"]].to_string(index=False))
    return df


def join(ventas: pd.DataFrame, costos: pd.DataFrame):
    # Si un nombre normalizado aparece más de una vez en la maestra (dos SKU
    # distintos con nombre parecido tras normalizar), nos quedamos con el
    # primero y avisamos — mejor revisar a mano esos casos.
    dup_norms = costos[costos.duplicated("norm", keep=False)].sort_values("norm")
    costos_dedup = costos.drop_duplicates("norm", keep="first")

    merged = ventas.merge(
        costos_dedup[["norm", "c", "Producto", "Categoria"]],
        on="norm", how="left", suffixes=("", "_maestra"),
    )

    # Segunda pasada: para lo que no calzó directo, probar los alias conocidos
    # (plural/singular, variantes sin distinguir, etc.)
    aliased_rows = []
    for idx in merged.index[merged["c"].isna()]:
        key = merged.at[idx, "norm"]
        candidates = ALIASES.get(key)
        if not candidates:
            continue
        costs = costos[costos["norm"].isin(candidates)]["c"]
        if costs.empty:
            continue
        merged.at[idx, "c"] = costs.mean()
        aliased_rows.append((merged.at[idx, "Producto"], key, candidates, costs.mean(), len(costs) > 1))

    sin_costo = merged[merged["c"].isna()][["Local", "Producto", "q", "p"]].sort_values(
        "q", ascending=False
    )
    no_vendidos = costos_dedup[~costos_dedup["norm"].isin(ventas["norm"])][
        ["SKU", "Producto", "Categoria"]
    ]

    out = merged[["Local", "Producto", "q", "p", "c"]].copy()
    return out, sin_costo, no_vendidos, dup_norms, aliased_rows


def build_dataset(ventas_raw: pd.DataFrame, maestra_path):
    """Versión importable (la usa el dashboard): mismo cruce que main(), sin prints
    de reporte ni sys.exit. Devuelve (dataset Local/Producto/q/p/c, sin_costo,
    precio_cero, aliased_rows)."""
    ventas, cero = prepare_ventas(ventas_raw)
    out, sin_costo, _, _, aliased_rows = join(ventas, load_costos(maestra_path))
    return out[out["c"].notna()].reset_index(drop=True), sin_costo, cero, aliased_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ventas", required=True, help="Excel de ventas (Local, Producto, q, p) — salida de justo_fetch_sales.py")
    ap.add_argument("--maestra", required=True, help="Excel 'MAESTRA KOKAI COSTOS PRODUCCION'")
    ap.add_argument("--output", default="ventas_con_costo.xlsx")
    args = ap.parse_args()

    print(f"Leyendo ventas desde {args.ventas}...")
    ventas = load_ventas(args.ventas)
    print(f"  {len(ventas)} filas (Local x Producto).")

    print(f"Leyendo costos desde {args.maestra} ({len(CATEGORY_SHEETS)} hojas de categoría)...")
    costos = load_costos(args.maestra)
    print(f"  {len(costos)} platos con costo de receta.")

    out, sin_costo, no_vendidos, dup_norms, aliased_rows = join(ventas, costos)

    n_total = len(out)
    n_con_costo = out["c"].notna().sum()
    n_sin_costo = n_total - n_con_costo
    print(f"\nCruce: {n_con_costo}/{n_total} filas de venta encontraron costo "
          f"({100*n_con_costo/n_total:.0f}%).")

    if aliased_rows:
        unique_aliased = {(key): (producto, candidates, avg_cost, is_avg)
                           for producto, key, candidates, avg_cost, is_avg in aliased_rows}
        print(f"\n{len(unique_aliased)} nombre(s) se cruzaron vía alias (nombre de Justo distinto "
              f"al de la Maestra) — revisar si el costo usado tiene sentido:")
        for key, (producto, candidates, avg_cost, is_avg) in unique_aliased.items():
            nota = f"promedio de {candidates}" if is_avg else f"= {candidates[0]}"
            print(f"  - '{producto}' -> c={avg_cost:.0f} ({nota})")

    if not dup_norms.empty:
        print(f"\nAviso: {dup_norms['norm'].nunique()} nombre(s) normalizados tienen más de un "
              f"SKU en la maestra (se usó el primero para cada uno) — revisar si son platos distintos:")
        print(dup_norms[["SKU", "Producto", "Categoria", "norm"]].to_string(index=False))

    if n_sin_costo:
        print(f"\n{n_sin_costo} productos vendidos en Justo NO encontraron costo en la maestra "
              f"(posible combo/promo no listado, o nombre distinto) — representan "
              f"{sin_costo['q'].sum()} unidades vendidas en el período:")
        print(sin_costo.to_string(index=False))
        print("\n  -> Revisar a mano: o se agregan a la maestra, o se excluyen del análisis.")

    print(f"\n{len(no_vendidos)} platos de la maestra no aparecieron en las ventas del período "
          f"(normal si no todo el menú se vendió en esas fechas).")

    out_con_costo = out[out["c"].notna()].reset_index(drop=True)
    out_con_costo.to_excel(args.output, index=False)
    print(f"\nEscrito: {args.output} ({len(out_con_costo)} filas con Local, Producto, q, p, c)")
    print("Listo para pasarle a kokai_menu_optimizer.py con --input y --sheet (hoja única, sin encabezado extra).")


if __name__ == "__main__":
    sys.exit(main())
