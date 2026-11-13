"""Exportación de la tabla de recomendaciones (ya filtrada) a CSV o Excel."""

from io import BytesIO

import pandas as pd


def to_csv(t: pd.DataFrame) -> bytes:
    return t.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")  # abre bien en Excel en español


def to_excel(t: pd.DataFrame, notas: list[str]) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        t.to_excel(xw, sheet_name="Recomendaciones", index=False)
        pd.DataFrame({"Notas": notas}).to_excel(xw, sheet_name="Notas", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(
                    60, max(12, max(len(str(c.value)) if c.value is not None else 0 for c in col[:60]) + 2))
    return buf.getvalue()
