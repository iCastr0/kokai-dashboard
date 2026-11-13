#!/usr/bin/env python3
"""
justo_fetch_sales.py
=====================

Descarga ventas por producto desde la API pública de Justo (POS de Kokai) y
las deja en el formato que necesita `kokai_menu_optimizer.py`.

REQUISITO: un token Bearer de la API de Justo (ver sección "Credenciales"
en el README). Mientras no lo tengan, este script se puede probar igual con
--dry-run (usa datos de ejemplo con la misma forma que la API real, no
necesita internet ni token).

JUSTO TIENE DOS APIs DISTINTAS — IMPORTANTE
---------------------------------------------
- **v3** (`api.service.getjusto.com/v3`): token tipo JWT, se obtiene en
  developers.getjusto.com con un flujo de autorización que la marca debe
  aprobar. Endpoint de ventas: `GET /tabs/{storeId}/tabs`.
- **v2** (`api.getjusto.com/api/v2`): "API Key" que se crea directo en el
  panel de Justo, en Plataforma > API > API Keys. Endpoint de ventas:
  `GET /orders`. Es la que más fácilmente consigue un local (Kokai la tiene).

Las dos usan el header `Authorization: Bearer <token>`, pero NO son
intercambiables: si mandas una API Key de v2 al endpoint de v3 (o viceversa)
da error `401 jwt malformed`. Este script detecta solo cuál versión es tu
token (si tiene forma de JWT asume v3, si no, v2) — se puede forzar con
`--api v2` / `--api v3` si detecta mal.

QUÉ HACE
--------
1. Llama al endpoint de ventas que corresponda (v2: `GET /orders`, v3:
   `GET /tabs/{storeId}/tabs`) para cada local, paginando, entre --from y
   --to.
2. Se queda solo con las líneas de producto vendido (descarta delivery fee,
   service fee, etc.).
3. **Valida que cada pedido realmente pertenezca al local pedido** y
   descarta (avisando) los que no — Justo puede devolver pedidos de OTROS
   locales si el storeId que le pasaste no es válido, en vez de dar error.
4. Agrega por (Local, Producto[, Canal]): suma cantidad, precio promedio
   ponderado por cantidad.
5. Escribe un Excel con columnas Local, Producto, q, p (y Canal, si se pide
   desglosar) — listo para juntar con el costo (columna `c`) desde la
   Maestra de costos y pasarle todo a kokai_menu_optimizer.py.

USO (con credenciales reales, API v2 — la más probable)
-----------------------------------------------------------
    python3 justo_fetch_sales.py \\
        --store-id "<ID externo Peñalolén>:Kokai Peñalolén" \\
        --store-id "<ID externo Vitacura>:Kokai Vitacura" \\
        --store-id "<ID externo Ñuñoa>:Kokai Ñuñoa" \\
        --from 2026-09-27 --to 2026-10-27 \\
        --output ventas_justo.xlsx

(el token va en el .env, no en la línea de comando — ver README)

USO SIN CREDENCIALES (para probar que el script funciona)
-----------------------------------------------------------
    python3 justo_fetch_sales.py --dry-run --output ventas_justo_ejemplo.xlsx

PRIMER PASO CON TOKEN REAL: averiguar el storeId de cada local
-----------------------------------------------------------------
    python3 justo_fetch_sales.py --list-stores

- Si tu token es v3: llama a GET /v3/api/me y te imprime cada local con su
  storeId real.
- Si tu token es v2: no hay endpoint público para listar locales, así que
  trae una muestra reciente de pedidos (sin filtrar por local) y te
  imprime los storeId/nombres de local que aparecen ahí — compáralos con
  el "ID externo" que configuraste en el panel para confirmar cuál es cuál.

Ver justo_fetch_sales_README.md para el detalle completo (cómo conseguir
el storeId de cada local, cómo juntar esto con el costo, límites de la API,
etc.)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    requests = None  # solo se necesita en modo real, no en --dry-run

BASE_URL_V3 = "https://api.service.getjusto.com/v3"
BASE_URL_V2 = "https://api.getjusto.com/api/v2"
BASE_URL = BASE_URL_V3  # compatibilidad con el resto del código v3 que ya existía


def detect_api_version(token: str) -> str:
    """v3 usa tokens con forma de JWT (header.payload.signature, 2 puntos,
    arranca con 'eyJ'); la API Key de v2 normalmente no tiene esa forma."""
    parts = (token or "").split(".")
    looks_like_jwt = len(parts) == 3 and token.startswith("eyJ")
    return "v3" if looks_like_jwt else "v2"


def _load_dotenv_next_to_script():
    """Carga variables desde un archivo .env que esté junto a este script
    (ej. JUSTO_API_TOKEN=...), sin pisar una variable que ya exista en el
    entorno. No requiere ninguna librería externa."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv_next_to_script()


def _say(on_progress, msg: str, frac: float | None = None):
    """Reporta progreso: al callback `on_progress(msg, frac)` si hay uno (la UI
    del dashboard), o a stdout si no (CLI). `frac` es 0..1 o None."""
    if on_progress is not None:
        on_progress(msg, frac)
    else:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# 0. Listar los locales reales de la marca (para obtener el storeId correcto)
# ---------------------------------------------------------------------------

def list_stores_v3(token: str):
    """Llama a GET /v3/api/me y devuelve (brand_name, [{'_id', 'name', 'timezone'}, ...])."""
    if requests is None:
        raise RuntimeError("Falta la librería 'requests' (pip install requests) para llamar a la API real.")

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL_V3}/api/me", headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Error {resp.status_code} llamando a /v3/api/me: {resp.text[:500]}")

    payload = resp.json()
    data = payload.get("data", payload)  # por si la respuesta no viene envuelta en {success, data}
    website = data.get("website", {})
    stores = data.get("stores", [])
    return website.get("name", "(sin nombre)"), stores


def list_stores_v2(token: str, sample_days: int = 14):
    """La v2 no tiene un endpoint público para listar locales. En vez de eso,
    trae una muestra reciente de pedidos (sin filtrar por local) y devuelve
    los storeId/nombres distintos que aparecen, para que el usuario pueda
    compararlos con el 'ID externo' que configuró en el panel."""
    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=sample_days)
    orders = fetch_orders_v2(
        token, store_ids=None,
        from_date=from_date.date().isoformat(), to_date=to_date.date().isoformat(),
        max_pages=3,
    )
    seen = {}
    for order in orders:
        store = order.get("store") or {}
        sid = order.get("storeId") or store.get("_id")
        name = store.get("name") or "(sin nombre)"
        if sid:
            seen.setdefault(sid, {"name": name, "n_pedidos": 0})
            seen[sid]["n_pedidos"] += 1
    return seen


# ---------------------------------------------------------------------------
# 1. Descarga desde la API real
# ---------------------------------------------------------------------------

def fetch_orders_v2(token: str, store_ids, from_date: str, to_date: str,
                     include_not_paid: bool = False, order_statuses=None,
                     max_retries: int = 3, sleep_between: float = 0.3, max_pages=None,
                     on_progress=None):
    """Pagina GET /api/v2/orders entre from_date y to_date. store_ids=None trae
    todos los locales de la marca (se usa solo para --list-stores). Devuelve
    lista de pedidos (orders), cada uno con 'storeId'/'store' e 'items'."""
    if requests is None:
        raise RuntimeError("Falta la librería 'requests' (pip install requests) para llamar a la API real.")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    all_orders = []
    page = 1
    while True:
        params = {
            "fromDate": from_date, "toDate": to_date, "page": page,
            "includeNotPaid": str(include_not_paid).lower(),
        }
        if store_ids:
            params["storesIds"] = store_ids  # requests serializa una lista como storesIds=a&storesIds=b
        if order_statuses:
            params["orderStatuses"] = order_statuses
        url = f"{BASE_URL_V2}/orders"
        _say(on_progress, f"  llamando a GET {url} (página {page}, fromDate={from_date}, toDate={to_date})...")

        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    _say(on_progress, f"    sin respuesta ({e.__class__.__name__}), reintentando...")
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"No hubo respuesta de Justo v2 tras {max_retries} intentos: {e}") from e
            if resp.status_code == 200:
                break
            if resp.status_code in (429, 500, 502, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Error {resp.status_code} llamando a Justo v2 (página {page}): {resp.text[:500]}")

        payload = resp.json()
        if payload.get("status") != "ok":
            raise RuntimeError(f"Justo v2 devolvió status != ok: {payload}")

        data = payload["data"]
        all_orders.extend(data["items"])
        _say(on_progress, f"  página {page} -> {len(data['items'])} pedidos "
                          f"(acumulado {len(all_orders)} de {data.get('totalCount', '?')})")

        if not data.get("hasNextPage") or (max_pages and page >= max_pages):
            break
        page += 1
        time.sleep(sleep_between)

    return all_orders


def orders_to_rows_v2(orders: list, local_name_by_store_id: dict, on_progress=None) -> pd.DataFrame:
    """Convierte pedidos v2 a filas, descartando (y avisando) los pedidos
    que vengan de un local distinto al que se pidió — Justo puede devolver
    pedidos de OTROS locales si el storeId pasado no es válido."""
    rows = []
    unexpected = {}
    for order in orders:
        store = order.get("store") or {}
        store_id = order.get("storeId") or store.get("_id")
        local_name = local_name_by_store_id.get(store_id)
        if local_name is None:
            label = f"{store_id} ({store.get('name', '?')})"
            unexpected[label] = unexpected.get(label, 0) + 1
            continue
        pedido = order.get("_id") or order.get("id") or f"sin-id-{len(rows)}"
        for item in order.get("items", []):
            product = item.get("product") or {}
            rows.append({
                "Local": local_name,
                "pedido": pedido,
                "Producto": (product.get("name") or "").strip(),
                "cantidad": item.get("amount", 0),
                "precio_unitario": item.get("unitPrice", 0),
                "Canal": order.get("deliveryType", "desconocido"),
                "fecha": order.get("createdAt"),
            })
    if unexpected:
        _say(on_progress, "  Aviso: se descartaron pedidos de locales NO pedidos (storeId inválido o mal mapeado):")
        for label, n in unexpected.items():
            _say(on_progress, f"    - {label}: {n} pedido(s) descartado(s)")
        _say(on_progress, "  Revisa el storeId que usaste para ese --store-id contra `--list-stores`.")
    return pd.DataFrame(rows)


def fetch_tabs(token: str, store_id: str, from_date: str, to_date: str,
                page_limit: int = 100, max_retries: int = 3, sleep_between: float = 0.3,
                on_progress=None):
    """Pagina GET /tabs/{storeId}/tabs entre from_date y to_date. Devuelve lista de tabs."""
    if requests is None:
        raise RuntimeError("Falta la librería 'requests' (pip install requests) para llamar a la API real.")

    headers = {"Authorization": f"Bearer {token}"}
    all_tabs = []
    page = 1
    while True:
        params = {
            "fromDate": from_date, "toDate": to_date,
            "page": page, "limit": page_limit,
            "sortBy": "createdAt", "sortType": "asc",
        }
        url = f"{BASE_URL}/tabs/{store_id}/tabs"

        for attempt in range(max_retries):
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                break
            if resp.status_code in (429, 500, 502, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(
                f"Error {resp.status_code} llamando a Justo (store {store_id}, página {page}): {resp.text[:500]}"
            )

        payload = resp.json()
        if not payload.get("success", False):
            raise RuntimeError(f"Justo devolvió success=false: {payload.get('error')}")

        data = payload["data"]
        all_tabs.extend(data["items"])
        _say(on_progress, f"  store {store_id}: página {page} -> {len(data['items'])} tabs "
                          f"(acumulado {len(all_tabs)} de {data.get('totalCount', '?')})")

        if not data.get("hasNextPage"):
            break
        page += 1
        time.sleep(sleep_between)  # buena práctica, no pegarle a la API sin pausa

    return all_tabs


# ---------------------------------------------------------------------------
# 2. Datos de ejemplo (misma forma que la respuesta real) para --dry-run
# ---------------------------------------------------------------------------

def sample_tabs():
    """Simula la respuesta de GET /tabs/{storeId}/tabs, con la forma real documentada."""
    return [
        {
            "_id": "t1", "source": "pos", "createdAt": "2026-10-20T19:05:00Z",
            "items": [
                {"type": "product", "productId": "p1", "productName": "Tori Panko", "amount": 2, "unitPrice": 6977, "price": 13954},
                {"type": "product", "productId": "p2", "productName": "Camarón Acevichado", "amount": 1, "unitPrice": 8325, "price": 8325},
                {"type": "deliveryFee", "productName": "Delivery", "amount": 1, "unitPrice": 1500, "price": 1500},
            ],
        },
        {
            "_id": "t2", "source": "ubereats", "createdAt": "2026-10-20T20:30:00Z",
            "items": [
                {"type": "product", "productId": "p1", "productName": "Tori Panko", "amount": 1, "unitPrice": 7200, "price": 7200},
                {"type": "product", "productId": "p3", "productName": "Coreano", "amount": 3, "unitPrice": 7396, "price": 22188},
            ],
        },
        {
            "_id": "t3", "source": "justo", "createdAt": "2026-10-21T13:10:00Z",
            "items": [
                {"type": "product", "productId": "p2", "productName": "Camarón Acevichado", "amount": 2, "unitPrice": 8100, "price": 16200},
                {"type": "serviceFee", "productName": "Servicio", "amount": 1, "unitPrice": 500, "price": 500},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 3. Agregación: de tabs a tabla Local / Producto / q / p (y Canal opcional)
# ---------------------------------------------------------------------------

def tabs_to_rows(tabs: list, local_name: str) -> pd.DataFrame:
    rows = []
    for tab in tabs:
        for item in tab.get("items", []):
            if item.get("type") != "product":
                continue  # descarta delivery fee, service fee, billingItem, etc.
            rows.append({
                "Local": local_name,
                "pedido": tab.get("_id") or f"sin-id-{len(rows)}",
                "Producto": item.get("productName", "").strip(),
                "cantidad": item.get("amount", 0),
                "precio_unitario": item.get("unitPrice", 0),
                "Canal": tab.get("source", "desconocido"),
                "fecha": tab.get("createdAt"),
            })
    return pd.DataFrame(rows)


def aggregate(df: pd.DataFrame, by_channel: bool) -> pd.DataFrame:
    group_cols = ["Local", "Producto"] + (["Canal"] if by_channel else [])

    def agg_group(g):
        qsum = g["cantidad"].sum()
        p = (g["cantidad"] * g["precio_unitario"]).sum() / qsum if qsum else 0
        return pd.Series({"q": qsum, "p": p})

    out = df.groupby(group_cols, as_index=False).apply(agg_group, include_groups=False)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. API de alto nivel (la usa el dashboard; la CLI de abajo no cambia)
# ---------------------------------------------------------------------------

class JustoConfigError(RuntimeError):
    """Falta configuración local (token o storeId) — no es un error de red."""


STORE_ENV_VARS = {
    "JUSTO_STORE_ID_PENALOLEN": "Kokai Peñalolén",
    "JUSTO_STORE_ID_VITACURA": "Kokai Vitacura",
    "JUSTO_STORE_ID_NUNOA": "Kokai Ñuñoa",
}


def stores_from_env() -> dict:
    """{storeId: nombre del local} según las variables JUSTO_STORE_ID_* del .env."""
    return {os.environ[var].strip(): name
            for var, name in STORE_ENV_VARS.items() if os.environ.get(var, "").strip()}


def fetch_sales(from_date: str, to_date: str, stores: dict | None = None, token: str | None = None,
                api: str | None = None, include_not_paid: bool = False, on_progress=None) -> pd.DataFrame:
    """Descarga y agrega ventas (Local, Producto, q, p) de todos los locales, uno
    por uno, informando el avance por `on_progress(msg, frac)`. from_date/to_date
    en YYYY-MM-DD. Lanza JustoConfigError si falta token/storeId y RuntimeError
    si la API falla o no hay ventas."""
    token = token or os.environ.get("JUSTO_API_TOKEN")
    if not token:
        raise JustoConfigError("Falta JUSTO_API_TOKEN en el archivo .env de 02_scripts/justo_integracion.")
    stores = stores or stores_from_env()
    if not stores:
        raise JustoConfigError(
            "Faltan los storeId de los locales: descomenta y completa JUSTO_STORE_ID_PENALOLEN, "
            "JUSTO_STORE_ID_VITACURA y JUSTO_STORE_ID_NUNOA en el .env de 02_scripts/justo_integracion."
        )
    api = api or detect_api_version(token)
    # Un día extra al final: los pedidos de la noche en Chile ya son el día siguiente en UTC. Se recortan
    # abajo con la fecha local.
    api_to = (datetime.fromisoformat(to_date) + timedelta(days=1)).date().isoformat()

    frames = []
    for i, (store_id, local_name) in enumerate(stores.items()):
        frac = i / len(stores)
        _say(on_progress, f"Descargando {local_name} ({i + 1} de {len(stores)})...", frac)

        def sub(msg, _frac=None, _name=local_name, _f=frac):
            _say(on_progress, f"{_name}: {msg.strip()}", _f)

        if api == "v2":
            orders = fetch_orders_v2(token, [store_id], from_date, api_to,
                                     include_not_paid=include_not_paid, on_progress=sub)
            frames.append(orders_to_rows_v2(orders, {store_id: local_name}, on_progress=sub))
        else:
            from_iso = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc).isoformat()
            to_iso = datetime.fromisoformat(api_to).replace(tzinfo=timezone.utc).isoformat()
            frames.append(tabs_to_rows(fetch_tabs(token, store_id, from_iso, to_iso, on_progress=sub), local_name))

    rows = pd.concat(frames, ignore_index=True)
    if not rows.empty and "fecha" in rows:
        # Solo pedidos dentro de [from_date, to_date) en hora de Chile: no depende de si la API trata
        # toDate como inclusivo, ni corta los pedidos de la noche (createdAt viene en UTC).
        f = pd.to_datetime(rows["fecha"], utc=True, errors="coerce").dt.tz_convert("America/Santiago").dt.date
        keep = f.isna() | ((f >= datetime.fromisoformat(from_date).date()) & (f < datetime.fromisoformat(to_date).date()))
        rows = rows[keep]
    if rows.empty:
        raise RuntimeError("Justo no devolvió ventas de producto para ese período.")
    _say(on_progress, "Agregando ventas por local y producto...", 1.0)
    out = aggregate(rows, by_channel=False)
    # Para el ticket promedio: pedidos con al menos un plato y venta total (con IVA) por local.
    rows["monto"] = rows["cantidad"] * rows["precio_unitario"]
    g = rows.groupby("Local")
    out.attrs["por_local"] = {loc: {"pedidos": int(g["pedido"].nunique()[loc]), "venta_bruta": float(g["monto"].sum()[loc])}
                              for loc in g.groups}
    return out


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------

def parse_store_id(spec: str):
    """'abc123:Kokai Peñalolén' -> ('abc123', 'Kokai Peñalolén')"""
    if ":" not in spec:
        raise ValueError(f"--store-id debe ser 'ID:Nombre del local', recibí: {spec!r}")
    store_id, name = spec.split(":", 1)
    return store_id.strip(), name.strip()


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--token", default=None,
                    help="Token Bearer de la API de Justo. Mejor no pasarlo aquí: "
                         "déjalo en la variable de entorno JUSTO_API_TOKEN y omite este flag.")
    p.add_argument("--store-id", action="append", default=[],
                    help="'<storeId>:<Nombre del local>' — repetir una vez por local. "
                         "En v2 este storeId es el 'ID externo' que configuraste en el panel de Justo.")
    p.add_argument("--api", choices=["v2", "v3"], default=None,
                    help="Forzar la versión de API (v2=API Key de panel, v3=OAuth/JWT). "
                         "Si no se pasa, se detecta sola según la forma del token.")
    p.add_argument("--include-not-paid", action="store_true",
                    help="(solo v2) Incluir pedidos no pagados en el resultado. Por defecto solo pagados.")
    p.add_argument("--from", dest="from_date", default=None, help="Fecha inicio, YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", default=None, help="Fecha fin, YYYY-MM-DD")
    p.add_argument("--output", default="ventas_justo.xlsx", help="Excel de salida")
    p.add_argument("--by-channel", action="store_true",
                    help="Desglosar también por canal (Canal como columna extra en vez de agregarlo todo junto)")
    p.add_argument("--dry-run", action="store_true",
                    help="No llama a la API real: usa datos de ejemplo para probar que el script funciona")
    p.add_argument("--list-stores", action="store_true",
                    help="Solo imprime los locales de la marca (storeId real + nombre) usando el token, y termina")
    return p.parse_args()


def main():
    args = parse_args()

    token = args.token or os.environ.get("JUSTO_API_TOKEN")
    api_version = args.api or (detect_api_version(token) if token else None)

    if args.list_stores:
        if not token:
            sys.exit(
                "Falta el token. Pónlo en la variable de entorno JUSTO_API_TOKEN "
                "(export JUSTO_API_TOKEN=\"...\") o pásalo con --token."
            )
        print(f"Detecté API {api_version} según la forma del token (usa --api para forzar otra).\n")

        if api_version == "v3":
            brand_name, stores = list_stores_v3(token)
            if not stores:
                print(f"Marca: {brand_name} — la API no devolvió ningún local para este token.")
                return
            print(f"Marca: {brand_name}\n")
            print(f"{'Nombre en Justo':35} storeId")
            print("-" * 70)
            for s in stores:
                print(f"{str(s.get('name', '?'))[:35]:35} {s.get('_id', '?')}")
            print(
                "\nUsa estos storeId en --store-id, por ejemplo:\n"
                f"  --store-id \"{stores[0].get('_id','<storeId>')}:{stores[0].get('name','Nombre')}\""
            )
        else:
            print("API v2: no hay endpoint para listar locales directamente. "
                  "Traigo una muestra de pedidos recientes (últimos 14 días, sin filtrar por local) "
                  "para ver qué storeId/nombres aparecen:\n")
            seen = list_stores_v2(token)
            if not seen:
                print("No aparecieron pedidos en los últimos 14 días para ningún local. "
                      "Prueba de nuevo con un rango de fechas más amplio corriendo el script normal "
                      "sin --store-id (si tu cuenta lo permite) o pide el storeId directo a Justo.")
                return
            print(f"{'Nombre en Justo':35} storeId{'':10}pedidos vistos")
            print("-" * 80)
            for sid, info in seen.items():
                print(f"{info['name'][:35]:35} {sid:30} {info['n_pedidos']}")
            print(
                "\nCompara estos storeId con el 'ID externo' que pusiste en el panel para cada local "
                "(deberían verse parecidos/iguales si está bien configurado). Úsalos en --store-id, "
                "por ejemplo:\n"
                f"  --store-id \"{list(seen.keys())[0]}:{list(seen.values())[0]['name']}\""
            )
        return

    if args.dry_run:
        print("Modo --dry-run: usando datos de ejemplo (misma forma que la API real), sin llamar a Justo.\n")
        all_rows = tabs_to_rows(sample_tabs(), "Kokai Ejemplo")
    else:
        args.token = token
        if not args.token:
            sys.exit(
                "Falta el token. Pónlo en la variable de entorno JUSTO_API_TOKEN "
                "(export JUSTO_API_TOKEN=\"...\") o pásalo con --token. "
                "Mientras no tengan credenciales, usen --dry-run para probar el script."
            )
        if not args.store_id:
            sys.exit("Falta al menos un --store-id 'ID:Nombre del local'.")
        if not args.from_date or not args.to_date:
            sys.exit("Faltan --from y --to (YYYY-MM-DD).")

        print(f"Detecté API {api_version} según la forma del token (usa --api para forzar otra).\n")

        if api_version == "v2":
            id_to_name = {}
            for spec in args.store_id:
                store_id, local_name = parse_store_id(spec)
                id_to_name[store_id] = local_name
            print(f"Descargando pedidos de {len(id_to_name)} local(es)...")
            orders = fetch_orders_v2(
                args.token, list(id_to_name.keys()), args.from_date, args.to_date,
                include_not_paid=args.include_not_paid,
            )
            print(f"  {len(orders)} pedidos descargados en total.")
            all_rows = orders_to_rows_v2(orders, id_to_name)
        else:
            from_iso = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc).isoformat()
            to_iso = datetime.fromisoformat(args.to_date).replace(tzinfo=timezone.utc).isoformat()

            frames = []
            for spec in args.store_id:
                store_id, local_name = parse_store_id(spec)
                print(f"Descargando {local_name} (store {store_id})...")
                tabs = fetch_tabs(args.token, store_id, from_iso, to_iso)
                print(f"  {len(tabs)} tabs descargadas.")
                frames.append(tabs_to_rows(tabs, local_name))
            all_rows = pd.concat(frames, ignore_index=True)

    if all_rows.empty:
        sys.exit("No se encontraron ventas de producto en el período/datos dados.")

    out = aggregate(all_rows, by_channel=args.by_channel)
    out.to_excel(args.output, index=False)

    print(f"\n{len(out)} filas (Local{'+ Canal' if args.by_channel else ''} x Producto).")
    print(f"Escrito en: {args.output}")
    print(
        "\nSiguiente paso: este archivo tiene Local, Producto, q, p (ventas reales) pero NO tiene\n"
        "el costo (columna c) — eso sigue viniendo de la Maestra de costos, por receta. Hay que\n"
        "cruzar por nombre de producto (ver justo_fetch_sales_README.md, sección 'Juntar con el costo')\n"
        "antes de pasarle el resultado a kokai_menu_optimizer.py."
    )


if __name__ == "__main__":
    sys.exit(main())
