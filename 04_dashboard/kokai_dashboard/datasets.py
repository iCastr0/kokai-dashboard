"""Datasets disponibles: listado, metadata (fecha/período), guardado y validación de cargas manuales."""

import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from . import storage
from .config import DATA_DIR, DEFAULT_DATASET, MAESTRA_PATH
from kokai_menu_optimizer import REQUIRED_COLS, load_items

FUENTE_JUSTO = "Justo (API)"
_TS = re.compile(r"(\d{8})_(\d{4})")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]
_MES_EN_NOMBRE = re.compile(r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*[_-]?(\d{4})", re.I)


@dataclass
class DatasetInfo:
    path: Path
    generado: datetime
    fuente: str
    desde: str | None = None
    hasta: str | None = None
    dias: int | None = None
    meta: dict = field(default_factory=dict)

    @property
    def periodo(self) -> str:
        if self.desde and self.hasta:
            d = lambda s: datetime.fromisoformat(s).strftime("%d/%m/%Y")
            n = f" ({self.dias} días)" if self.dias else ""
            return f"{d(self.desde)} al {d(self.hasta)}{n}"
        return "no informado"

    @property
    def mes(self) -> str:
        """«octubre 2026»: el mes que cubren las ventas (del período o, si no hay, del nombre del archivo)."""
        if self.desde and self.hasta:
            d0, d1 = datetime.fromisoformat(self.desde), datetime.fromisoformat(self.hasta)
            if (d0.year, d0.month) == (d1.year, d1.month):
                return f"{MESES[d0.month - 1]} {d0.year}"
            return f"{d0:%d/%m/%Y} al {d1:%d/%m/%Y}"
        if m := _MES_EN_NOMBRE.search(self.path.stem):
            i = [x[:3] for x in MESES].index(m.group(1).lower()[:3])
            return f"{MESES[i]} {m.group(2)}"
        return "período no informado"

    @property
    def label(self) -> str:
        return f"{self.generado:%d/%m/%Y %H:%M} · {self.fuente}"


def nombre_mes(d: date) -> str:
    return f"{MESES[d.month - 1]} {d.year}"


def ultimos_meses(n: int = 12) -> list[date]:
    """Primer día de los últimos n meses ya cerrados, del más reciente al más antiguo."""
    y, m = date.today().year, date.today().month
    out = []
    for _ in range(n):
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
        out.append(date(y, m, 1))
    return out


def rango_mes(ini: date) -> tuple[date, date]:
    """(primer día, último día) del mes que empieza en `ini`."""
    return ini, (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _sidecar(path: Path) -> Path:
    return path.with_suffix(".json")


def info_for(path: Path) -> DatasetInfo:
    meta = {}
    try:
        meta = json.loads(_sidecar(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if meta.get("generado"):
        generado = datetime.fromisoformat(meta["generado"])
    elif (m := _TS.search(path.stem)):
        generado = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    else:
        generado = datetime.fromtimestamp(path.stat().st_mtime)
    fuente = meta.get("fuente") or ("Entregable" if path == DEFAULT_DATASET else "Archivo cargado")
    return DatasetInfo(path, generado, fuente, meta.get("desde"), meta.get("hasta"), meta.get("dias"), meta)


def list_datasets() -> list[DatasetInfo]:
    paths = sorted(DATA_DIR.glob("*.xlsx")) if DATA_DIR.exists() else []
    if DEFAULT_DATASET.exists():
        paths.append(DEFAULT_DATASET)
    return sorted((info_for(p) for p in paths), key=lambda i: i.generado, reverse=True)


def default_dataset(infos: list[DatasetInfo]) -> DatasetInfo | None:
    """Al abrir: la última descarga desde Justo; si no hay, el entregable; si no, lo más reciente."""
    for i in infos:
        if i.fuente == FUENTE_JUSTO:
            return i
    for i in infos:
        if i.path == DEFAULT_DATASET:
            return i
    return infos[0] if infos else None


def save_dataset(df: pd.DataFrame, meta: dict, prefix: str = "ventas_con_costo") -> Path:
    """Guarda un dataset nuevo con fecha en el nombre, sin pisar los anteriores."""
    DATA_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    base = f"{prefix}_{now:%Y%m%d_%H%M}"
    path, n = DATA_DIR / f"{base}.xlsx", 2
    while path.exists():
        path = DATA_DIR / f"{base}_{n}.xlsx"
        n += 1
    df[REQUIRED_COLS].to_excel(path, index=False)
    _sidecar(path).write_text(
        json.dumps({**meta, "generado": now.isoformat(timespec="seconds")}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    storage.push(path, _sidecar(path))
    return path


def read_upload(uploaded) -> tuple[pd.DataFrame | None, str | None]:
    """Valida un archivo subido a mano. Devuelve (df, None) o (None, mensaje de error legible)."""
    suffix = Path(uploaded.name).suffix.lower()
    if suffix not in (".xlsx", ".xlsm", ".xls", ".csv"):
        return None, f"Formato «{suffix}» no soportado. Sube un Excel (.xlsx) o un CSV."
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        tmp.flush()
        try:
            raw = pd.read_csv(tmp.name) if suffix == ".csv" else pd.read_excel(tmp.name)
            if "c" not in raw.columns and {"Local", "Producto", "q", "p"} <= set(raw.columns):
                # Ventas sin costo (ej. exportadas de Justo): se cruzan con la Maestra como en «Actualizar».
                import join_ventas_costos as jvc
                df, sin_costo, _, _ = jvc.build_dataset(raw, MAESTRA_PATH)
                if df.empty:
                    return None, "Ningún producto del archivo encontró costo en la Maestra. ¿Los nombres son los de Justo?"
            else:
                df = load_items(tmp.name)
        except ValueError as e:
            return None, f"El archivo no tiene el formato esperado (Local, Producto, q, p y opcionalmente c). {e}"
        except Exception:
            return None, "No pude leer el archivo. ¿Es un Excel o CSV válido y no está dañado o protegido?"
    df = df[REQUIRED_COLS]
    bad = df[(df["q"] <= 0) | (df["p"] <= 0) | (df["c"] < 0)]
    if not bad.empty:
        return None, (f"{len(bad)} fila(s) con valores no válidos (cantidad o precio ≤ 0, o costo negativo). "
                      f"Primera: {bad.iloc[0]['Producto']} ({bad.iloc[0]['Local']}). Corrígelas y vuelve a subir.")
    return df.reset_index(drop=True), None
