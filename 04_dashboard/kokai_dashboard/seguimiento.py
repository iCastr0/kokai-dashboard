"""Parte 2 · Cómo saber si funcionó: los indicadores de un mes comparados con la línea base (el mes con el
que se armó el plan), con semáforo.

Las ventas y unidades se comparan POR DÍA, porque los meses no tienen el mismo largo. El ticket promedio
necesita el número de pedidos: viene solo en las descargas desde Justo (metadata «por_local»); para la línea
base o una carga manual se ingresa a mano y queda guardado en data/linea_base.json."""

import json
from dataclasses import dataclass

import pandas as pd

from . import analisis, datasets, engine, storage
from .config import (BASELINE_DATASET, DATA_DIR, DEFAULT_PARAMS, MIN_UNIDADES_PLATO, RANGE_MID, SEM_FC_HOLGURA,
                     SEM_TICKET, SEM_UNIDADES, SEM_VENTA)
from .context import _enrich, _plan

_TICKETS = DATA_DIR / "linea_base.json"  # tickets ingresados a mano: {nombre de archivo: ticket}


@dataclass
class Mes:
    info: object
    enriched: pd.DataFrame

    @property
    def dias(self) -> int:
        return self.info.dias or 30

    @property
    def fc(self) -> float:
        return analisis.food_cost(self.enriched)

    @property
    def venta_dia(self) -> float:
        return self.enriched["venta"].sum() / self.dias

    def ticket(self) -> float | None:
        """Venta con IVA ÷ pedidos. De la descarga de Justo si está; si no, lo ingresado a mano."""
        por_local = self.info.meta.get("por_local") or {}
        pedidos = sum(v.get("pedidos", 0) for v in por_local.values())
        if pedidos:
            return sum(v.get("venta_bruta", 0) for v in por_local.values()) / pedidos
        return tickets_manuales().get(self.info.path.name)


def tickets_manuales() -> dict:
    try:
        return json.loads(_TICKETS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_ticket(info, valor: float | None):
    t = tickets_manuales()
    if valor:
        t[info.path.name] = float(valor)
    else:
        t.pop(info.path.name, None)
    DATA_DIR.mkdir(exist_ok=True)
    _TICKETS.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    storage.push(_TICKETS)


def cargar(info) -> Mes:
    classified, _ = engine.get_classified(info.path)
    return Mes(info, _enrich(classified))


def linea_base():
    """(Mes línea base, plan armado con ese mes o None si falta calcular el optimizador)."""
    info = datasets.info_for(BASELINE_DATASET)
    base = cargar(info)
    r = engine.load_results(info.path, DEFAULT_PARAMS).get(RANGE_MID)
    if r is None:
        return base, None, None
    plan, totals = _plan(r[0], base.enriched, info, f"{info.path}|{info.dias}")
    return base, plan, totals


def semaforo(cambio: float, umbrales: tuple[float, float]) -> str:
    """verde si el cambio es ≥ el primer umbral, rojo si es < el segundo, amarillo entre medio."""
    verde, rojo = umbrales
    return "verde" if cambio >= verde else "rojo" if cambio < rojo else "amarillo"


def semaforo_fc(fc: float, fc_base: float, fc_objetivo: float) -> str:
    """verde si llega a lo que promete el plan (con una holgura), rojo si no bajó respecto de la línea base."""
    return "verde" if fc <= fc_objetivo + SEM_FC_HOLGURA else "rojo" if fc >= fc_base else "amarillo"


def unidades_ajustados(base: Mes, mes: Mes, plan: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unidades por día de los platos a los que el plan les sube el precio, línea base vs. mes.
    Devuelve (resumen por cuadrante + total, detalle por plato y local)."""
    ajust = plan.loc[plan["alza"] > 0, ["_norm", "Local", "Plato", "Cuadrante", "alza"]]
    key = lambda df: df.assign(Local=df["Local"].str.replace("Kokai ", ""))  # noqa: E731
    q0 = key(base.enriched).groupby(["Local", "_norm"])["q"].sum() / base.dias
    q1 = key(mes.enriched).groupby(["Local", "_norm"])["q"].sum() / mes.dias
    d = ajust.join(q0.rename("dia_base"), on=["Local", "_norm"]).join(q1.rename("dia_mes"), on=["Local", "_norm"])
    d["dia_mes"] = d["dia_mes"].fillna(0.0)  # no se vendió en el mes
    d["cambio"] = d["dia_mes"] / d["dia_base"] - 1
    d["unidades_base"] = d["dia_base"] * base.dias

    tot = d.groupby("Cuadrante")[["dia_base", "dia_mes"]].sum()
    tot.loc["Todos"] = tot.sum()
    tot["cambio"] = tot["dia_mes"] / tot["dia_base"] - 1
    tot["platos"] = d.groupby("Cuadrante").size().reindex(tot.index).fillna(len(d)).astype(int)
    tot["estado"] = [semaforo(c, SEM_UNIDADES) for c in tot["cambio"]]
    detalle = d[d["unidades_base"] >= MIN_UNIDADES_PLATO].sort_values("cambio")
    detalle["estado"] = [semaforo(c, SEM_UNIDADES) for c in detalle["cambio"]]
    return tot.reset_index(), detalle.reset_index(drop=True)


def indicadores(base: Mes, mes: Mes, plan: pd.DataFrame, totals: dict, fc_meta: float | None) -> list[dict]:
    """Los cuatro indicadores del mes con su línea base, meta y semáforo (estado None = falta el dato)."""
    fc_obj = fc_meta if fc_meta is not None else totals[RANGE_MID]["fc1"]
    tot, _ = unidades_ajustados(base, mes, plan)
    u = tot.set_index("Cuadrante").loc["Todos"]
    t0, t1 = base.ticket(), mes.ticket()
    v = mes.venta_dia / base.venta_dia - 1
    return [
        {"clave": "fc", "valor": mes.fc, "base": base.fc, "objetivo": fc_obj, "cambio_pts": (mes.fc - base.fc) * 100,
         "estado": semaforo_fc(mes.fc, base.fc, fc_obj)},
        {"clave": "unidades", "valor": u["dia_mes"], "base": u["dia_base"], "cambio": u["cambio"],
         "estado": u["estado"]},
        {"clave": "ticket", "valor": t1, "base": t0,
         "cambio": (t1 / t0 - 1) if t0 and t1 else None,
         "estado": semaforo(t1 / t0 - 1, SEM_TICKET) if t0 and t1 else None},
        {"clave": "venta", "valor": mes.venta_dia, "base": base.venta_dia, "cambio": v, "estado": semaforo(v, SEM_VENTA)},
    ]
