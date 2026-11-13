"""Números de negocio de la Parte 1: dónde se va la plata y el plan de acción.

Todo se expresa sobre venta NETA (precio de Justo ÷ 1,19), que es como se mide el food cost; el motor
trabaja con precio con IVA, pero las razones y las decisiones (alzas en %) no cambian por eso.

El plan traduce el escenario Base del optimizador a decisiones cargables:
- una decisión por plato y local, tal como la entrega el modelo (un plato puede subir en un local y no
  en otro);
- precios redondeados a precio de carta (terminados en 90) para cada canal;
- el efecto se re-evalúa con esos precios ya redondeados bajo las tres elasticidades: el extremo
  Conservador y el Optimista son el rango que se muestra, el Base es el valor central."""

import numpy as np
import pandas as pd

from . import maestra
from .config import (CLASS_LABEL, DEFAULT_ELASTICITY, FAMILIA, INSUMO_NOMBRE, IVA, PUSH_THRESHOLD, RANGE_HIGH,
                     RANGE_LOW, RANGE_MID)

PRIORIDADES = ["Hacer ya", "Probar", "Opcional"]
_MIN_PTS = 0.005  # una alza fuera del 80 % pasa a «Probar» si baja el food cost al menos esto (pts)
_PARETO = 0.80  # «Hacer ya»: los cambios que juntos explican el 80 % de la baja del food cost


def months(info) -> float:
    """Cuántos meses cubre el dataset: un mes calendario completo (ej. octubre) cuenta como 1. Sin período
    informado se asume un mes."""
    if info.desde and info.hasta:
        d0, d1 = pd.Timestamp(info.desde), pd.Timestamp(info.hasta)
        if d0.day == 1 and d1 == d0 + pd.offsets.MonthEnd(0):
            return 1.0
    return (info.dias / 30) if info.dias else 1.0


def enrich(classified: pd.DataFrame) -> pd.DataFrame:
    """Agrega SKU, categoría y familia de la Maestra, y venta neta / costo de insumos de cada fila."""
    catalogo, _, _ = maestra.load()
    m = [maestra.match_sku(p, catalogo) for p in classified["Producto"]]
    df = classified.copy()
    df["SKU"] = pd.array([s for s, _ in m], dtype="Int64")
    df["Categoria"] = [(c or "").strip() or "Sin categoría" for _, c in m]
    df["Familia"] = df["Categoria"].map(FAMILIA).fillna("Otros")
    df["venta"] = df["q"] * df["p"] / (1 + IVA)
    df["costo"] = df["q"] * df["c"]
    return df


def food_cost(df: pd.DataFrame) -> float:
    return df["costo"].sum() / df["venta"].sum()


def breakdown(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Venta neta, costo de insumos, food cost y peso en el gasto total, por local o por familia."""
    g = df.groupby(by).agg(venta=("venta", "sum"), costo=("costo", "sum"), unidades=("q", "sum"))
    g["fc"] = g["costo"] / g["venta"]
    g["peso"] = g["costo"] / g["costo"].sum()
    return g.sort_values("costo", ascending=False).reset_index()


def top_platos(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Platos que más plata se llevan en insumos (todos los locales juntos), no los de mayor %."""
    g = df.groupby("_norm").agg(Plato=("Producto", "first"), Familia=("Familia", "first"), unidades=("q", "sum"),
                                venta=("venta", "sum"), costo=("costo", "sum"))
    g["fc"] = g["costo"] / g["venta"]
    g["peso"] = g["costo"] / df["costo"].sum()
    return g.sort_values("costo", ascending=False).head(n).reset_index(drop=True)


def exposicion(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (local × plato × insumo): cuánto del costo de ese plato vendido es ese insumo."""
    _, _, insumos = maestra.load()
    x = df[["Local", "_norm", "Producto", "Familia", "SKU", "q", "c", "venta", "costo"]].dropna(subset=["SKU"]).merge(
        insumos.astype({"SKU": "Int64"}), on="SKU")
    x["Insumo"] = x["Insumo"].map(lambda s: INSUMO_NOMBRE.get(s, s))
    x["gasto"] = x["costo"] * x["fraccion"]
    return x


def gasto_insumos(df: pd.DataFrame) -> pd.DataFrame:
    """Gasto en cada insumo: el costo de cada plato vendido repartido según su receta."""
    g = exposicion(df).groupby("Insumo", as_index=False)["gasto"].sum().sort_values("gasto", ascending=False)
    total = df["costo"].sum()
    sin_receta = total - g["gasto"].sum()
    if sin_receta > 0.005 * total:
        g = pd.concat([g, pd.DataFrame({"Insumo": ["Platos sin receta desglosada"], "gasto": [sin_receta]})])
    g["peso"] = g["gasto"] / total
    return g.reset_index(drop=True)


def impacto_insumo(df: pd.DataFrame, insumo: str, alza: float) -> tuple[float, pd.DataFrame]:
    """(puntos que sube el food cost total, platos afectados) si `insumo` sube `alza` (0,10 = 10 %).
    Supone que se venden las mismas unidades a los mismos precios: es el efecto directo de la factura."""
    x = exposicion(df)
    x = x[x["Insumo"] == insumo]
    dpts = x["gasto"].sum() * alza / df["venta"].sum() * 100
    g = x.groupby("_norm").agg(Plato=("Producto", "first"), Familia=("Familia", "first"), unidades=("q", "sum"),
                               venta=("venta", "sum"), costo=("costo", "sum"), gasto=("gasto", "sum"))
    g["peso_insumo"] = g["gasto"] / g["costo"]
    g["fc_hoy"] = g["costo"] / g["venta"]
    g["fc_nuevo"] = (g["costo"] + g["gasto"] * alza) / g["venta"]
    g["costo_extra"] = g["gasto"] * alza
    return dpts, g.sort_values("costo_extra", ascending=False).reset_index(drop=True)


def sensibilidad(df: pd.DataFrame, alza: float, n: int = 10) -> pd.DataFrame:
    """Para los n insumos con más gasto: platos afectados y cuántos puntos sube el food cost si suben `alza`."""
    x = exposicion(df)
    g = x.groupby("Insumo").agg(gasto=("gasto", "sum"), platos=("_norm", "nunique"))
    g["pts"] = g["gasto"] * alza / df["venta"].sum() * 100
    g["costo_extra"] = g["gasto"] * alza
    return g.sort_values("gasto", ascending=False).head(n).reset_index()


def precio_piso(costo_receta: float, fc_objetivo: float) -> dict:
    """Precio mínimo de un plato nuevo: costo de receta ÷ food cost objetivo (neto), con IVA y llevado al
    precio de carta siguiente (terminado en 90, hacia arriba para no quedar bajo el piso)."""
    neto = costo_receta / fc_objetivo
    bruto = neto * (1 + IVA)
    carta = np.ceil((bruto + 10) / 100) * 100 - 10
    return {"neto": neto, "bruto": bruto, "carta": float(carta), "fc_carta": costo_receta / (carta / (1 + IVA))}


def platos_estimados(df: pd.DataFrame) -> pd.DataFrame:
    """Platos cuyo costo no sale de una receta propia: cruzados por alias (a veces el promedio de variantes
    que Justo no distingue) o sin receta desglosada en la Maestra (bebidas, algunos gunkan)."""
    from join_ventas_costos import ALIASES, norm_name
    _, _, insumos = maestra.load()
    con_receta = set(insumos["SKU"])
    rows = []
    for norm, g in df.groupby("_norm"):
        nombre, key = g["Producto"].iloc[0], norm_name(g["Producto"].iloc[0])
        motivos = []
        if key in ALIASES:
            n = len(ALIASES[key])
            motivos.append(f"promedio de {n} variantes de la Maestra" if n > 1 else "cruzado por nombre parecido")
        if pd.isna(g["SKU"].iloc[0]) or int(g["SKU"].iloc[0]) not in con_receta:
            motivos.append("sin receta desglosada")
        if motivos:
            rows.append({"Plato": nombre, "Motivo": " · ".join(motivos), "Unidades": g["q"].sum(),
                         "Peso en el costo": g["costo"].sum() / df["costo"].sum()})
    return pd.DataFrame(rows).sort_values("Unidades", ascending=False).reset_index(drop=True)


# --- Plan de acción --------------------------------------------------------------------------------

def round_carta(x: float) -> float:
    """Precio de carta: al múltiplo de 100 más cercano, terminado en 90 (8.990, 9.390, 12.490…)."""
    return max(90.0, round((x + 10) / 100) * 100 - 10)


def _accion(clase: str, alza: float, u: float) -> str:
    parts = []
    if alza > 0:
        parts.append(f"Subir {alza * 100:.0f} %" + (" o achicar porción" if clase == "Caballo de batalla" else ""))
    if u > PUSH_THRESHOLD:
        parts.append("Más visibilidad")
    elif u < -PUSH_THRESHOLD:
        parts.append("Sacar o rediseñar" if clase == "Perro" else "Menos visibilidad")
    return " · ".join(parts) or "Mantener"


def _evaluate(rows: pd.DataFrame, scen: str) -> pd.DataFrame:
    """Unidades, venta neta y costo de cada fila (local × plato) con el plan aplicado, en un escenario."""
    eps = rows["clase"].map(DEFAULT_ELASTICITY[scen]).to_numpy()
    q1 = rows["q"] * (1 + rows["u"]) * np.power(1 + rows["alza"], eps)
    return pd.DataFrame({"q1": q1, "venta1": q1 * rows["p"] * (1 + rows["alza"]) / (1 + IVA), "costo1": q1 * rows["c"]},
                        index=rows.index)


def build_plan(out_base: pd.DataFrame, enriched: pd.DataFrame, info):
    """(plan por plato y local, totales por escenario). out_base = resultado del optimizador, escenario Base."""
    _, precios, _ = maestra.load()
    rows = out_base.merge(enriched[["Local", "Producto", "SKU", "Familia", "venta", "costo"]], on=["Local", "Producto"])
    rows = rows.merge(precios.astype({"SKU": "Int64"}), on="SKU", how="left")
    rows["Salón"] = rows["Salón"].fillna(rows["p"].map(round_carta))  # sin precio de lista: el vendido

    # La alza efectiva es la del precio de salón ya redondeado a precio de carta.
    rows["alza"] = [round_carta(r * (1 + d)) / r - 1 for r, d in zip(rows["Salón"], rows["delta_precio"])]
    rows.loc[rows["delta_precio"] < 0.005, "alza"] = 0.0  # alzas que el modelo no pidió no aparecen por redondeo
    rows["alza"] = rows["alza"].clip(lower=0.0)
    rows["u"] = rows["u_mezcla"]

    m = months(info)
    venta0, costo0 = rows["venta"].sum(), rows["costo"].sum()
    fc0 = costo0 / venta0
    totals = {}
    for scen in (RANGE_LOW, RANGE_MID, RANGE_HIGH):
        e = _evaluate(rows, scen)
        v1, c1 = e["venta1"].sum(), e["costo1"].sum()
        totals[scen] = {"fc0": fc0, "fc1": c1 / v1, "venta0": venta0 / m, "venta1": v1 / m,
                        "margen0": (venta0 - costo0) / m, "margen1": (v1 - c1) / m,
                        "unidades0": rows["q"].sum() / m, "unidades1": e["q1"].sum() / m}
        # Efecto por fila, aditivo: la suma de las filas da exactamente el cambio total.
        rows[f"dmargen_{scen}"] = ((e["venta1"] - e["costo1"]) - (rows["venta"] - rows["costo"])) / m
        rows[f"dfc_{scen}"] = ((e["costo1"] - fc0 * e["venta1"]) - (rows["costo"] - fc0 * rows["venta"])) / v1

    plan = pd.DataFrame({
        "_norm": rows["_norm"], "Plato": rows["Producto"], "Local": rows["Local"].str.replace("Kokai ", ""),
        "SKU": rows["SKU"], "Familia": rows["Familia"], "Cuadrante": rows["clase"],
        "Unidades/mes": rows["q"] / m, "alza": rows["alza"], "u": rows["u"],
        "Efecto FC (pts)": rows[f"dfc_{RANGE_MID}"] * 100, "Efecto $/mes": rows[f"dmargen_{RANGE_MID}"],
        "_min": rows[f"dmargen_{RANGE_LOW}"], "_max": rows[f"dmargen_{RANGE_HIGH}"],
    })
    for ch in maestra.CHANNELS:
        plan[f"{ch} actual"] = rows[ch]
        plan[f"{ch} sugerido"] = [round_carta(a * (1 + d)) if pd.notna(a) and d > 0 else a
                                  for a, d in zip(rows[ch], rows["alza"])]
    plan["Acción"] = [_accion(c, a, u) for c, a, u in zip(plan["Cuadrante"], plan["alza"], plan["u"])]
    plan["Prioridad"] = _prioridad(plan)
    plan["Cuadrante"] = plan["Cuadrante"].map(CLASS_LABEL)
    plan = plan.sort_values(["Prioridad", "Efecto $/mes"], key=_prio_key, ascending=[True, False])
    return plan.reset_index(drop=True), totals


def _prio_key(col: pd.Series):
    return col.map({p: i for i, p in enumerate(PRIORIDADES + ["—"])}) if col.name == "Prioridad" else col


def _prioridad(plan: pd.DataFrame) -> list[str]:
    """Se ordena por cuánto baja el food cost (el objetivo del proyecto), no por pesos: un cambio de
    visibilidad resta margen al plato pero lo suma en los platos hacia donde se mueve la venta.
    Hacer ya: los cambios que juntos explican el 80 % de la baja del food cost — salvo los de estrellas,
    que se prueban primero (son el corazón de la carta). Probar: esas estrellas, y otras alzas de precio
    que bajan el food cost en forma visible. Opcional: el resto (aportes chicos). «—»: no hay cambio."""
    cambia = (plan["alza"] > 0) | (plan["u"].abs() > PUSH_THRESHOLD)
    baja = (-plan["Efecto FC (pts)"]).where(cambia, 0).clip(lower=0).sort_values(ascending=False)
    total = baja.sum()
    top = set(baja.index[(baja.cumsum() - baja) < _PARETO * total]) if total > 0 else set()
    out = []
    for i, r in plan.iterrows():
        if not cambia[i]:
            out.append("—")
        elif i in top and r["Cuadrante"] != "Estrella":
            out.append("Hacer ya")
        elif i in top or (r["alza"] > 0 and baja[i] >= _MIN_PTS):
            out.append("Probar")
        else:
            out.append("Opcional")
    return out


def decisiones(plan: pd.DataFrame, insumos: pd.DataFrame) -> list[str]:
    """Las 3–5 decisiones del resumen, en una frase cada una, a partir del plan."""
    from .fmt import clp, num

    def ej(s: pd.DataFrame, k: int = 3) -> str:
        n = s.groupby("Plato")["Unidades/mes"].sum().sort_values(ascending=False).index[:k].tolist()
        return ", ".join(n[:-1]) + " y " + n[-1] if len(n) > 1 else (n[0] if n else "")

    out = []
    ya = plan[(plan["Prioridad"] == "Hacer ya") & (plan["alza"] > 0)]
    if len(ya):
        lo, hi = ya["alza"].min() * 100, ya["alza"].max() * 100
        rng = f"{lo:.0f} %" if round(lo) == round(hi) else f"entre {lo:.0f} y {hi:.0f} %"
        out.append(f"**Subir {rng} el precio de {ya["Plato"].nunique()} platos de alta venta** ({ej(ya)}): aportan cerca de "
                   f"{clp(round(ya['Efecto $/mes'].sum(), -3))} al mes.")
    vis = plan[(plan["Cuadrante"] == "Puzzles") & (plan["u"] > PUSH_THRESHOLD)]
    if len(vis):
        out.append(f"**Dar visibilidad en la carta y en las apps a {vis["Plato"].nunique()} puzzles** — dejan buen margen pero se "
                   f"venden poco ({ej(vis)}).")
    perros = plan[(plan["Cuadrante"] == "Perros") & (plan["u"] < -PUSH_THRESHOLD)]
    if len(perros):
        out.append(f"**Sacar o rediseñar {perros["Plato"].nunique()} perros**, empezando por los que menos venden; hoy suman "
                   f"{num(perros['Unidades/mes'].sum())} unidades al mes.")
    est = plan[plan["Cuadrante"] == "Estrellas"]
    if len(est):
        out.append(f"**No tocar receta ni porción de las {est["Plato"].nunique()} estrellas** ({ej(est)}); si se les sube el "
                   "precio, probarlo primero en un local.")
    top = insumos[insumos["Insumo"] != "Platos sin receta desglosada"].head(3)
    if len(top):
        out.append(f"**Vigilar el precio de {', '.join(top['Insumo'].iloc[:-1])} y {top['Insumo'].iloc[-1]}**: "
                   f"son el {top['peso'].sum() * 100:.0f} % del gasto en insumos.")
    return out[:5]
