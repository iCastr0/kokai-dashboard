#!/usr/bin/env python3
"""
kokai_menu_optimizer.py  (v2)
=============================

Clasificación Kasavana-Smith (menu engineering) + optimización de precio
y mezcla para el proyecto Kokai (Capstone Ing. Civil Industrial, UAI).

Esta versión reemplaza la v1 (grid search de 4 variables por cuadrante) por
el modelo oficial presentado en Avance 3: un programa no lineal con DOS
variables de decisión POR PLATO, resuelto con un solver real (SLSQP de
scipy), más la deduplicación de productos que la revisión del 21-oct-2026
encontró pendiente. Ver kokai_menu_optimizer_README.md para el detalle
completo (fórmulas, supuestos, cómo actualizar con datos del piloto).

QUÉ HACE
--------
1. Lee un archivo de ítems de menú (Excel o CSV): Local, Producto, q, p, c
   (y Categoria, opcional).
2. Normaliza nombres de producto y FUSIONA duplicados (mismo plato con
   nombres distintos, ej. "Sake nikkei" / "Sake Nikkei (tartar de salmon)").
3. Clasifica cada ítem (Estrella / Caballo de batalla / Puzzle / Perro) por
   local, con el método Kasavana-Smith.
4. Optimiza, sobre TODO el menú a la vez (ambos locales juntos, como en
   Avance 3), dos variables por plato:
     - δᵢ: alza de precio neto
     - uᵢ: empuje de mezcla (venta inducida por mérchandising/sugerencia de
       venta, no por precio) — esto es lo que permite decidir "a qué plato
       empujarle venta y a cuál no", independiente del precio.
   Demanda resultante: qᵢ = q₀ᵢ (1+uᵢ)(1+δᵢ)^εᵢ
   Minimiza el food cost total, sujeto a:
     - las unidades totales no caen más de X% (--max-units-drop)
     - el margen en pesos no baja del actual
     - Σ q₀ᵢ uᵢ = 0  (la mezcla mueve ventas entre platos, no las crea)
   Resuelto con scipy.optimize.minimize, method="SLSQP" (programación
   cuadrática secuencial) — un solver real, no una búsqueda al azar.
5. Corre esto en 3 escenarios de elasticidad (Conservador/Base/Optimista) y
   escribe todo a un Excel de resultados.

USO
---
    python3 kokai_menu_optimizer.py --input datos_items.xlsx --output resultados.xlsx

Con datos reales de un piloto de elasticidad ya medidos, pasarlos con
--elasticities (ver README).
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# CONFIGURACIÓN POR DEFECTO
# ---------------------------------------------------------------------------

CLASSES = ["Estrella", "Caballo de batalla", "Puzzle", "Perro"]
COLOR = {
    "Estrella": "D1FAE5",
    "Caballo de batalla": "FEF3C7",
    "Puzzle": "DBEAFE",
    "Perro": "FEE2E2",
}

# Elasticidad-precio ASUMIDA por cuadrante y escenario. Estos son los valores
# oficiales presentados en Avance 3 (lámina "modelo"), no los de la v1 de
# este script — unificados a pedido de la revisión del 21-oct-2026.
# Reemplazar por valores medidos en terreno (piloto de precio) en cuanto
# existan — ver README.
DEFAULT_ELASTICITY = {
    "Conservador": {"Estrella": -0.7, "Caballo de batalla": -1.0, "Puzzle": -1.3, "Perro": -1.6},
    "Base":        {"Estrella": -0.4, "Caballo de batalla": -0.6, "Puzzle": -0.9, "Perro": -1.2},
    "Optimista":   {"Estrella": -0.2, "Caballo de batalla": -0.3, "Puzzle": -0.5, "Perro": -0.8},
}
SCENARIOS = list(DEFAULT_ELASTICITY.keys())

# Rango de la variable de precio (δ) y de la variable de mezcla (u), igual
# para todos los platos — así se presentó en Avance 3. Si quieren límites
# distintos por cuadrante, usar --bounds (ver README).
DEFAULT_BOUND_DELTA = (0.00, 0.05)   # 0% a +5% de alza de precio
DEFAULT_BOUND_U = (-0.05, 0.05)      # -5% a +5% de empuje de mezcla

# Cuánto puede caer el total de unidades vendidas (restricción dura).
DEFAULT_MAX_UNITS_DROP = 0.02  # 2%

# El precio p de los datos (Justo / carta) incluye IVA; el costo de receta c es neto. Margen, ingreso y
# food cost se calculan con el precio NETO (p / (1 + IVA)) para comparar peras con peras.
IVA = 0.19


# ---------------------------------------------------------------------------
# 1. CARGA Y NORMALIZACIÓN DE DATOS (incluye fusión de duplicados)
# ---------------------------------------------------------------------------

REQUIRED_COLS = ["Local", "Producto", "q", "p", "c"]


def load_items(input_path: str, sheet: str | None = None) -> pd.DataFrame:
    path = Path(input_path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(path, sheet_name=sheet or 0)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Formato no soportado: {path.suffix}. Usa .xlsx o .csv")

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas obligatorias: {missing}. Columnas encontradas: {list(df.columns)}."
        )
    if "Categoria" not in df.columns:
        df["Categoria"] = "—"
    if "est" not in df.columns:
        df["est"] = "No"

    df = df.dropna(subset=REQUIRED_COLS).copy()
    for col in ("q", "p", "c"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["q", "p", "c"])
    if df.empty:
        raise ValueError("El archivo de entrada no tiene filas válidas tras limpiar datos.")
    return df


def _normalize_name(name: str) -> str:
    """minúsculas, sin tildes, sin sufijos entre paréntesis, sin espacios extra."""
    s = str(name).strip().lower()
    s = re.sub(r"\(.*?\)", "", s).strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"\s+", " ", s)
    return s


def dedupe_items(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Fusiona filas que son el mismo plato con nombres distintos (mismo Local,
    mismo nombre normalizado). q se suma; p y c se promedian ponderados por
    q (precio/costo "representativo" del plato fusionado); Categoria toma el
    primer valor real disponible; est queda "Sí" si alguna de las filas
    fusionadas tenía costo estimado.

    Esto corrige el hallazgo de la revisión del 21-oct-2026: en el archivo
    de demanda v6, 3 platos de Vitacura aparecen duplicados (ej. "Sake
    nikkei" / "Sake Nikkei (tartar de salmon)"), lo que antes inflaba n y
    distorsionaba el umbral de popularidad (0,7/n) y la clase de esos
    platos.
    """
    df = df.copy()
    df["_norm"] = df["Producto"].apply(_normalize_name)

    dup_mask = df.duplicated(["Local", "_norm"], keep=False)
    if verbose and dup_mask.any():
        print("Duplicados detectados y fusionados:")
        for (local, norm), g in df[dup_mask].groupby(["Local", "_norm"]):
            nombres = ", ".join(g["Producto"].tolist())
            print(f"  - {local}: {nombres}  ->  fusionados en un solo ítem")

    def merge_group(g: pd.DataFrame) -> pd.Series:
        qsum = g["q"].sum()
        p = (g["q"] * g["p"]).sum() / qsum
        c = (g["q"] * g["c"]).sum() / qsum
        cat = next((x for x in g["Categoria"] if x != "—"), "—")
        est = "Sí" if (g["est"] == "Sí").any() else "No"
        # nombre representativo: el más corto / sin paréntesis
        nombre = sorted(g["Producto"], key=lambda s: ("(" in s, len(s)))[0]
        return pd.Series({"Producto": nombre, "Categoria": cat, "q": qsum, "p": p, "c": c, "est": est})

    merged = df.groupby(["Local", "_norm"], as_index=False).apply(merge_group, include_groups=False)
    merged = merged.reset_index(drop=True)
    if verbose:
        print(f"Filas antes de fusionar: {len(df)} -> después: {len(merged)}")
    return merged


# ---------------------------------------------------------------------------
# 2. CLASIFICACIÓN KASAVANA-SMITH
# ---------------------------------------------------------------------------

def classify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["CM"] = df["p"] / (1 + IVA) - df["c"]  # margen por plato en pesos, neto de IVA
    out = []
    for local, g in df.groupby("Local"):
        g = g.copy()
        n = len(g)
        g["mix"] = g["q"] / g["q"].sum()
        cm_bar = (g["q"] * g["CM"]).sum() / g["q"].sum()
        umbral = 0.7 / n
        popular = g["mix"] >= umbral
        alto_margen = g["CM"] >= cm_bar
        g["clase"] = np.select(
            [popular & alto_margen, popular & ~alto_margen, ~popular & alto_margen],
            ["Estrella", "Caballo de batalla", "Puzzle"],
            default="Perro",
        )
        g["CM_promedio_ponderado"] = cm_bar
        g["umbral_mix"] = umbral
        out.append(g)
    return pd.concat(out).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. OPTIMIZACIÓN: NLP real (SLSQP), 2 variables por plato, TODO el menú junto
# ---------------------------------------------------------------------------

def run_scenario(df: pd.DataFrame, elasticity: dict, bound_delta, bound_u,
                  max_units_drop: float, maxiter: int = 300):
    """
    df: la tabla clasificada COMPLETA (todos los locales juntos — así se
    optimiza en Avance 3: un solo problema de 2*n variables, no uno por
    local).
    """
    n = len(df)
    q0 = df["q"].values
    p0 = df["p"].values / (1 + IVA)  # precio neto: ingreso, margen y food cost sin IVA
    c0 = df["c"].values
    eps = np.array([elasticity[k] for k in df["clase"]])

    rev0 = (q0 * p0).sum()
    cost0 = (q0 * c0).sum()
    margin0 = rev0 - cost0
    units0 = q0.sum()

    def unpack(x):
        return x[:n], x[n:]

    def q_of(delta, u):
        return q0 * (1 + u) * np.power(1 + delta, eps)

    def fc_obj(x):
        delta, u = unpack(x)
        q = q_of(delta, u)
        rev = (p0 * (1 + delta) * q).sum()
        cost = (c0 * q).sum()
        return cost / rev

    def g_units(x):
        delta, u = unpack(x)
        q = q_of(delta, u)
        return q.sum() - (1 - max_units_drop) * units0

    def g_margin(x):
        delta, u = unpack(x)
        q = q_of(delta, u)
        rev = (p0 * (1 + delta) * q).sum()
        cost = (c0 * q).sum()
        return (rev - cost) - margin0

    def h_mix(x):
        _, u = unpack(x)
        return (q0 * u).sum()

    bounds = [bound_delta] * n + [bound_u] * n
    x0 = np.zeros(2 * n)  # δ=0, u=0 es un punto de partida FACTIBLE (cumple las 3 restricciones)
    cons = [
        {"type": "ineq", "fun": g_units},
        {"type": "ineq", "fun": g_margin},
        {"type": "eq", "fun": h_mix},
    ]
    res = minimize(fc_obj, x0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"maxiter": maxiter, "ftol": 1e-10})

    delta, u = unpack(res.x)
    q = q_of(delta, u)
    rev = (p0 * (1 + delta) * q).sum()
    cost = (c0 * q).sum()
    margin = rev - cost

    out = df.copy()
    out["delta_precio"] = delta           # fracción, ej. 0.05 = +5%
    out["u_mezcla"] = u                   # fracción, ej. -0.03 = -3% de empuje
    out["q_nuevo"] = q
    out["p_nuevo"] = df["p"].values * (1 + delta)  # con IVA, como el precio de carta
    out["ingreso_actual"] = q0 * p0  # neto de IVA
    out["ingreso_nuevo"] = p0 * (1 + delta) * q

    summary = {
        "solver_success": bool(res.success),
        "solver_message": str(res.message),
        "rev0": rev0, "fc0": cost0 / rev0, "rev_new": rev, "fc_new": cost / rev,
        "margin0": margin0, "margin_new": margin,
        "units0": units0, "units_new": q.sum(),
    }
    return out, summary


def run_all(df_classified: pd.DataFrame, elasticities: dict, bound_delta, bound_u,
            max_units_drop: float, maxiter: int = 300):
    results = {}
    for scen in SCENARIOS if set(SCENARIOS) <= set(elasticities) else list(elasticities.keys()):
        out, summ = run_scenario(df_classified, elasticities[scen], bound_delta, bound_u, max_units_drop, maxiter)
        results[scen] = (out, summ)
    return results


# ---------------------------------------------------------------------------
# 4. ESCRITURA DEL EXCEL DE RESULTADOS
# ---------------------------------------------------------------------------

def write_output(df_classified: pd.DataFrame, results: dict, output_path: str,
                  max_units_drop: float, dedup_log: list[str]):
    wb = Workbook()
    hdr = PatternFill("solid", fgColor="1F2937")
    hf = Font(bold=True, color="FFFFFF")

    # --- Hoja 1: clasificación -------------------------------------------------
    ws = wb.active
    ws.title = "Clasificacion"
    ws.append(["Clasificación Kasavana-Smith (después de fusionar duplicados)"])
    ws["A1"].font = Font(bold=True, size=13)
    if dedup_log:
        ws.append(["Duplicados fusionados:"] + [])
        for line in dedup_log:
            ws.append([line])
    ws.append([])
    ws.append(["Local", "Clase", "N° ítems", "% mezcla", "Ingreso actual sin IVA ($)", "Margen food ($)"])
    for cell in ws[ws.max_row]:
        cell.fill = hdr
        cell.font = hf
    for local, g in df_classified.groupby("Local"):
        for k in CLASSES:
            s = g[g["clase"] == k]
            if s.empty:
                continue
            ws.append([local, k, len(s), s["mix"].sum(), (s["q"] * s["p"]).sum() / (1 + IVA), (s["q"] * s["CM"]).sum()])
            row = ws.max_row
            ws.cell(row, 2).fill = PatternFill("solid", fgColor=COLOR[k])
            ws.cell(row, 4).number_format = "0.0%"
            for j in (5, 6):
                ws.cell(row, j).number_format = "#,##0"
    for i, w in enumerate([20, 22, 10, 10, 18, 16], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # --- Hoja 2: escenarios -----------------------------------------------------
    ws2 = wb.create_sheet("Escenarios")
    ws2.append([
        f"Optimización conjunta (precio δ + mezcla u por plato, SLSQP) — "
        f"tope de caída de unidades: {max_units_drop*100:.0f}%, margen en pesos ≥ actual"
    ])
    ws2["A1"].font = Font(bold=True, size=12)
    ws2.append([])
    ws2.append([
        "Escenario", "Solver", "FC actual", "FC logrado", "Δ FC (pts)",
        "Ingreso actual sin IVA ($)", "Ingreso nuevo sin IVA ($)", "Δ Ingreso %",
        "Margen actual ($)", "Margen nuevo ($)", "Δ Margen %",
        "Unidades actual", "Unidades nuevas", "Δ Unidades %",
    ])
    for cell in ws2[ws2.max_row]:
        cell.fill = hdr
        cell.font = hf
        cell.alignment = Alignment(wrap_text=True)
    for scen, (out, s) in results.items():
        ws2.append([
            scen, "OK" if s["solver_success"] else f"REVISAR: {s['solver_message']}",
            s["fc0"], s["fc_new"], (s["fc0"] - s["fc_new"]) * 100,
            s["rev0"], s["rev_new"], s["rev_new"] / s["rev0"] - 1,
            s["margin0"], s["margin_new"], s["margin_new"] / s["margin0"] - 1,
            s["units0"], s["units_new"], s["units_new"] / s["units0"] - 1,
        ])
        row = ws2.max_row
        for j in (3, 4, 8, 11, 14):
            ws2.cell(row, j).number_format = "0.0%" if j != 5 else "0.00"
        ws2.cell(row, 5).number_format = "0.00"
        for j in (6, 7, 9, 10):
            ws2.cell(row, j).number_format = "#,##0"
        for j in (12, 13):
            ws2.cell(row, j).number_format = "#,##0"
    for i, w in enumerate([14, 22, 10, 10, 10, 15, 15, 10, 15, 15, 11, 12, 12, 11], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # --- Hoja 3: resumen por clase, escenario Base ------------------------------
    if "Base" in results:
        out, _ = results["Base"]
        ws3 = wb.create_sheet("Resumen por clase (Base)")
        ws3.append(["Clase", "N° platos", "Alza de precio media (ponderada por venta)",
                    "Δ unidades %", "Δ ingreso %"])
        for cell in ws3[1]:
            cell.fill = hdr
            cell.font = hf
        for k, g in out.groupby("clase"):
            avg_delta = (g["q_nuevo"] * g["delta_precio"]).sum() / g["q_nuevo"].sum()
            unidades0 = g["q"].sum()
            unidades1 = g["q_nuevo"].sum()
            ing0 = g["ingreso_actual"].sum()
            ing1 = g["ingreso_nuevo"].sum()
            ws3.append([k, len(g), avg_delta, unidades1 / unidades0 - 1, ing1 / ing0 - 1])
            row = ws3.max_row
            ws3.cell(row, 1).fill = PatternFill("solid", fgColor=COLOR[k])
            for j in (3, 4, 5):
                ws3.cell(row, j).number_format = "0.0%"
        for i, w in enumerate([20, 10, 30, 12, 12], 1):
            ws3.column_dimensions[get_column_letter(i)].width = w

    # --- Hoja 4+: detalle por producto, escenario Base --------------------------
    if "Base" in results:
        out, _ = results["Base"]
        ws4 = wb.create_sheet("Detalle por producto (Base)")
        cols = ["Local", "Producto", "clase", "q", "p", "delta_precio", "p_nuevo",
                "u_mezcla", "q_nuevo", "ingreso_actual", "ingreso_nuevo"]
        names = ["Local", "Producto", "Clase", "Cantidad actual", "Precio actual ($)",
                 "Δ Precio (δ)", "Precio nuevo ($)", "Empuje de mezcla (u)", "Cantidad nueva",
                 "Ingreso actual sin IVA ($)", "Ingreso nuevo sin IVA ($)"]
        ws4.append(names)
        for cell in ws4[1]:
            cell.fill = hdr
            cell.font = hf
        for _, x in out.sort_values(["Local", "clase", "q"], ascending=[True, True, False])[cols].iterrows():
            ws4.append([x[c] for c in cols])
            row = ws4.max_row
            ws4.cell(row, 3).fill = PatternFill("solid", fgColor=COLOR[x["clase"]])
            ws4.cell(row, 6).number_format = "0.0%"   # delta_precio es fracción -> 0.0% correcto (NO en puntos)
            ws4.cell(row, 8).number_format = "0.0%"   # u_mezcla, idem
            for j in (4, 5, 7, 9, 10, 11):
                ws4.cell(row, j).number_format = "#,##0"
        ws4.freeze_panes = "C2"
        for i, w in enumerate([18, 32, 18, 13, 13, 11, 13, 14, 13, 15, 15], 1):
            ws4.column_dimensions[get_column_letter(i)].width = w

    wb.save(output_path)


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, help="Excel o CSV con columnas Local, Producto, q, p, c")
    p.add_argument("--sheet", default=None, help="Nombre o índice de la hoja, si --input es .xlsx")
    p.add_argument("--output", default="resultados_menu_engineering.xlsx", help="Excel de salida")
    p.add_argument("--max-units-drop", type=float, default=DEFAULT_MAX_UNITS_DROP,
                    help="Caída máxima tolerada de unidades totales, como fracción (default: 0.02 = 2%%)")
    p.add_argument("--bound-delta", default=None,
                    help='JSON [min,max] para δ (alza de precio), ej. "[0,0.08]". Default: [0, 0.05]')
    p.add_argument("--bound-u", default=None,
                    help='JSON [min,max] para u (empuje de mezcla), ej. "[-0.1,0.1]". Default: [-0.05, 0.05]')
    p.add_argument("--elasticities", default=None,
                    help='JSON anidado {"Escenario": {"Clase": valor, ...}, ...} para reemplazar '
                         'los supuestos por defecto (ej. con el resultado del piloto de precio). '
                         'También acepta un JSON plano {"Clase": valor} que se aplica solo al '
                         'escenario "Base".')
    p.add_argument("--no-dedup", action="store_true",
                    help="No fusionar productos duplicados (usar solo si ya vienen limpios)")
    return p.parse_args()


def main():
    args = parse_args()

    elasticities = {k: dict(v) for k, v in DEFAULT_ELASTICITY.items()}
    if args.elasticities:
        raw = args.elasticities
        payload = json.loads(Path(raw).read_text()) if Path(raw).exists() else json.loads(raw)
        if set(payload.keys()) & set(CLASSES):
            # JSON plano -> sólo pisa el escenario Base
            elasticities["Base"].update(payload)
        else:
            for scen, overrides in payload.items():
                elasticities.setdefault(scen, dict(DEFAULT_ELASTICITY.get(scen, DEFAULT_ELASTICITY["Base"])))
                elasticities[scen].update(overrides)

    bound_delta = tuple(json.loads(args.bound_delta)) if args.bound_delta else DEFAULT_BOUND_DELTA
    bound_u = tuple(json.loads(args.bound_u)) if args.bound_u else DEFAULT_BOUND_U

    print(f"Límites: δ (precio) en {bound_delta}, u (mezcla) en {bound_u}")
    print(f"Tope de caída de unidades: {args.max_units_drop:.1%}")
    print(f"Elasticidades: {json.dumps(elasticities, ensure_ascii=False)}")

    df = load_items(args.input, args.sheet)

    dedup_log = []
    if not args.no_dedup:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            df = dedupe_items(df, verbose=True)
        dedup_log = buf.getvalue().splitlines()
        print(buf.getvalue())

    df_classified = classify(df)

    results = run_all(df_classified, elasticities, bound_delta, bound_u, args.max_units_drop)

    print()
    for scen, (out, s) in results.items():
        flag = "OK" if s["solver_success"] else f"REVISAR ({s['solver_message']})"
        print(f"{scen} [{flag}]: FC {s['fc0']:.2%} -> {s['fc_new']:.2%} "
              f"({(s['fc0']-s['fc_new'])*100:.2f} pts), "
              f"margen {s['margin0']:,.0f} -> {s['margin_new']:,.0f} "
              f"({s['margin_new']/s['margin0']-1:+.1%}), "
              f"unidades {s['units_new']/s['units0']-1:+.1%}")

    write_output(df_classified, results, args.output, args.max_units_drop, dedup_log)
    print(f"\nListo. Resultados escritos en: {args.output}")


if __name__ == "__main__":
    sys.exit(main())
