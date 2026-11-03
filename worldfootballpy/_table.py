"""Emulación de ``rvest::html_table()`` + ``data.frame()`` de R.

worldfootballR depende mucho de cómo R nombra las columnas al convertir una
tabla HTML: la primera fila de encabezado se usa como nombres (pasados por
``make.names(unique = TRUE)`` y con ``Var.<i>`` para los vacíos) y la segunda
fila de encabezado queda como primera fila de datos. Las funciones de limpieza
de nombres (``.rename_fb_cols`` y similares) se apoyan en ese comportamiento,
así que lo reproducimos aquí para obtener los mismos nombres de columna.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

_R_RESERVED = {
    "if", "else", "repeat", "while", "function", "for", "next", "break", "TRUE", "FALSE",
    "NULL", "Inf", "NaN", "NA", "NA_integer_", "NA_real_", "NA_character_", "in",
}


def text(el) -> str:
    """Texto de un nodo con espacios recortados (``html_text(trim=TRUE)``)."""
    if el is None:
        return ""
    return (el.text_content() or "").strip()


def raw_text(el) -> str:
    if el is None:
        return ""
    return el.text_content() or ""


def _cell_text(cell) -> str:
    # rvest convierte <br> en salto de línea y recorta espacios
    for br in cell.iter("br"):
        br.tail = "\n" + (br.tail or "")
    return re.sub(r"[ \t\r\f\v]+", " ", cell.text_content() or "").strip()


def _int_attr(cell, name):
    try:
        v = int(cell.get(name, "1"))
        return v if v > 0 else 1
    except (TypeError, ValueError):
        return 1


def table_rows(table) -> list[list[str]]:
    """Filas de la tabla con colspan/rowspan expandidos (como rvest)."""
    rows = table.xpath(".//tr")
    grid: list[list[str]] = []
    pending: dict[int, tuple[str, int]] = {}  # columna -> (texto, filas restantes)
    for tr in rows:
        cells = tr.xpath("./td|./th")
        out: list[str] = []
        col = 0
        ci = 0
        while ci < len(cells) or col in pending:
            if col in pending:
                val, left = pending[col]
                out.append(val)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (val, left - 1)
                col += 1
                continue
            cell = cells[ci]
            ci += 1
            val = _cell_text(cell)
            cs = _int_attr(cell, "colspan")
            rs = _int_attr(cell, "rowspan")
            for _ in range(cs):
                out.append(val)
                if rs > 1:
                    pending[col] = (val, rs - 1)
                col += 1
        grid.append(out)
    return grid


def make_names(names, unique: bool = True) -> list[str]:
    """Reproduce ``make.names(names, unique = TRUE)`` de R."""
    out = []
    for n in names:
        n = "" if n is None else str(n)
        n = re.sub(r"[^\w.]", ".", n, flags=re.UNICODE)
        if n == "":
            n = "X"
        elif re.match(r"^(\d|_|\.\d)", n):
            n = "X" + n
        if n in _R_RESERVED:
            n = n + "."
        out.append(n)
    return make_unique(out) if unique else out


def make_unique(names) -> list[str]:
    """Reproduce ``make.unique(names, sep='.')`` de R."""
    seen = set(names)
    counts: dict[str, int] = {}
    result = []
    used = set()
    for n in names:
        if n not in used:
            used.add(n)
            result.append(n)
            continue
        k = counts.get(n, 0)
        while True:
            k += 1
            cand = f"{n}.{k}"
            if cand not in used and cand not in seen:
                break
        counts[n] = k
        used.add(cand)
        result.append(cand)
    return result


def r_df_names(header) -> list[str]:
    """Nombres que tendría ``data.frame(html_table(x))`` en R."""
    names = []
    for i, h in enumerate(header, start=1):
        names.append(f"Var.{i}" if (h is None or str(h) == "") else str(h))
    # make.names sobre los nombres no vacíos; Var.i ya es válido
    return make_names(names, unique=True)


def _type_convert(values: pd.Series) -> pd.Series:
    """Emula ``type.convert``: columna numérica si todos los no vacíos lo son."""
    s = values.astype(object)
    stripped = s.map(lambda v: v if isinstance(v, str) else ("" if v is None else str(v)))
    non_empty = stripped[(stripped != "") & (stripped != "NA")]
    if len(non_empty) == 0:
        # columna vacía -> lógica NA en R
        return pd.Series([np.nan] * len(s), index=s.index, dtype=float)
    num = pd.to_numeric(non_empty, errors="coerce")
    if num.notna().all() and not non_empty.str.contains(r"^\s*0x", case=False).any():
        full = pd.to_numeric(stripped.replace({"": np.nan, "NA": np.nan}), errors="coerce")
        return full
    lowered = non_empty.str.upper()
    if lowered.isin(["TRUE", "FALSE", "T", "F"]).all():
        return stripped.map(lambda v: np.nan if v in ("", "NA") else v.upper() in ("TRUE", "T"))
    return stripped.replace({"NA": np.nan})


def html_table(table, header=None, convert: bool = True, r_names: bool = True) -> pd.DataFrame:
    """Convierte un elemento ``<table>`` igual que ``data.frame(rvest::html_table(x))``."""
    grid = table_rows(table)
    if not grid:
        return pd.DataFrame()
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    first_tr = table.xpath(".//tr")[0]
    first_cells = first_tr.xpath("./td|./th")
    if header is None:
        header = bool(first_cells) and all(c.tag == "th" for c in first_cells)
    if header:
        cols = grid[0]
        data = grid[1:]
    else:
        cols = [f"X{i}" for i in range(1, width + 1)]
        data = grid
    names = r_df_names(cols) if r_names else list(cols)
    df = pd.DataFrame(data, columns=range(width))
    if convert and len(df):
        for c in df.columns:
            df[c] = _type_convert(df[c])
    df.columns = names
    return df.reset_index(drop=True)


def html_tables(nodes, **kwargs) -> list[pd.DataFrame]:
    return [html_table(n, **kwargs) for n in nodes]


def bind_rows(frames) -> pd.DataFrame:
    """``dplyr::bind_rows``: concatena alineando columnas por nombre."""
    frames = [f for f in frames if f is not None and len(f.columns) > 0]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def first_row_as_char(df: pd.DataFrame) -> list[str]:
    """``df[1,] %>% as.character()``."""
    if len(df) == 0:
        return [""] * len(df.columns)
    out = []
    for v in df.iloc[0].tolist():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            out.append("NA")
        elif isinstance(v, float) and v.is_integer():
            out.append(str(int(v)))
        else:
            out.append(str(v))
    return out


__all__ = [
    "html_table", "html_tables", "table_rows", "make_names", "make_unique",
    "r_df_names", "bind_rows", "first_row_as_char", "text", "raw_text",
]

