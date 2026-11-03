"""Funciones internas traducidas de ``internals.R``."""

from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd

from . import _http
from ._table import first_row_as_char, html_table

FBREF = "https://fbref.com"
TM = "https://www.transfermarkt.com"
UNDERSTAT = "https://understat.com"
DATA_REPO_RAW = "https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master"
DATA_REPO_RELEASES = "https://github.com/JaseZiv/worldfootballR_data/releases/download"
ALL_COMPETITIONS_CSV = f"{DATA_REPO_RAW}/raw-data/all_leages_and_cups/all_competitions.csv"


# ----------------------------------------------------------------------------
# utilidades generales
# ----------------------------------------------------------------------------

def as_list(x):
    """Convierte escalares en lista (los argumentos de R suelen ser vectores)."""
    if x is None:
        return []
    if isinstance(x, (list, tuple, set, pd.Series, np.ndarray, range)):
        return list(x)
    return [x]


def is_na(x) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and np.isnan(x):
        return True
    try:
        return bool(pd.isna(x)) if not isinstance(x, (list, tuple)) else False
    except (TypeError, ValueError):
        return False


def squish(s):
    """``stringr::str_squish``."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return s
    return re.sub(r"\s+", " ", str(s)).strip()


def as_numeric(series):
    """``as.numeric`` con NA silencioso para valores no numéricos."""
    if isinstance(series, pd.Series):
        return pd.to_numeric(series, errors="coerce")
    try:
        return float(series)
    except (TypeError, ValueError):
        return np.nan


def clean_numeric(series: pd.Series) -> pd.Series:
    """``gsub(",", "") %>% gsub("+", "") %>% as.numeric``."""
    s = series.astype(object).map(
        lambda v: v.replace(",", "").replace("+", "").strip() if isinstance(v, str) else v
    )
    return pd.to_numeric(s, errors="coerce")


def numeric_cols(df: pd.DataFrame, exclude) -> pd.DataFrame:
    """Convierte a número todas las columnas salvo ``exclude`` (por posición: tolera nombres repetidos)."""
    exclude = set(exclude)
    for i, c in enumerate(list(df.columns)):
        if c not in exclude:
            df.isetitem(i, clean_numeric(df.iloc[:, i]))
    return df


def all_competitions() -> pd.DataFrame:
    """Tabla maestra de competiciones de worldfootballR_data."""
    return _http.read_csv_url(ALL_COMPETITIONS_CSV)


def progress(iterable, desc: str = ""):
    try:
        from tqdm.auto import tqdm

        return tqdm(iterable, desc=desc, leave=False)
    except ImportError:
        return iterable


def select(el, css):
    return el.cssselect(css)


def select_one(el, css):
    found = el.cssselect(css)
    return found[0] if found else None


def attr(nodes, name):
    return [n.get(name) for n in nodes]


def texts(nodes, trim: bool = True):
    return [((n.text_content() or "").strip() if trim else (n.text_content() or "")) for n in nodes]


def str_extract(s, pattern):
    if not isinstance(s, str):
        return np.nan
    m = re.search(pattern, s)
    return m.group(0) if m else np.nan


# ----------------------------------------------------------------------------
# limpieza de nombres de columnas (FBref)
# ----------------------------------------------------------------------------

def _apply(names, steps):
    out = []
    for n in names:
        for pat, rep in steps:
            n = re.sub(pat, rep, n)
        out.append(n)
    return out


def _joined(df):
    return [f"{a}_{b}" for a, b in zip(first_row_as_char(df), df.columns)]


_RENAME_FB = [
    (r"\..[0-9]", ""), (r"\.[0-9]", ""), (r"\.", "_"), (r"_Var", ""), (r"# Pl", "Num_Players"),
    (r"%", "_percent"), (r"_Performance", ""), (r"1/3", "Final_Third"), (r"\+/-", "Plus_Minus"),
    (r"/", "_per_"), (r"-", "_minus_"), (r"90s", "Mins_Per_90"), (r"__", "_"), (r"_$", ""),
]


def rename_fb_cols(df: pd.DataFrame) -> pd.DataFrame:
    """``.rename_fb_cols``."""
    names = _apply(_joined(df), _RENAME_FB)
    df = df.iloc[1:].copy()
    df.columns = names
    return df.reset_index(drop=True)


def clean_advanced_stat_table(table_el) -> pd.DataFrame:
    """``.clean_advanced_stat_table``."""
    df = rename_fb_cols(html_table(table_el))
    return numeric_cols(df, ["Squad"])


_PLAYER_SEASON = [
    (r"\..[0-9]", ""), (r"\.[0-9]", ""), (r"\.", "_"), (r"_Var", ""), (r"_Playing", ""),
    (r"%", "_percent"), (r"_Performance", ""), (r"1/3", "Final_Third"), (r"\+/-", "Plus_Minus"),
    (r"/", "_per_"), (r"-", "_minus_"), (r"90s", "Mins_Per_90"), (r"__", "_"),
]


def clean_player_season_stats(table_el) -> pd.DataFrame:
    """``.clean_player_season_stats``."""
    raw = html_table(table_el)
    names = _apply(_joined(raw), _PLAYER_SEASON)
    df = raw.iloc[1:].copy()
    df.columns = names
    df = df.reset_index(drop=True)
    if "Matches" in df.columns:
        df = df.drop(columns=["Matches"])
    season = df["Season"].astype(str)
    hits = np.where(season.str.contains("Season", regex=False))[0]
    if len(hits):
        df = df.iloc[: hits.min()].copy()
    cols = [c for c in df.columns if c not in ("Season", "Squad", "Comp")]
    df["Squad"] = df["Squad"].astype(str).str.replace(r"^[^A-Z]*([A-Z].*)", r"\1", regex=True)
    if "Country" in cols:
        df["Country"] = df["Country"].astype(str).str.replace(r"^.*? ([A-Z])", r"\1", regex=True)
        cols.remove("Country")
    if "LgRank" in cols:
        cols.remove("LgRank")
    for c in cols:
        df[c] = clean_numeric(df[c])
    return df.reset_index(drop=True)


_MATCH_ADV = [
    (r"\..[0-9]", ""), (r"\.[0-9]", ""), (r"\.", "_"), (r"_Var", ""), (r"#", "Player_Num"),
    (r"%", "_percent"), (r"_Performance", ""), (r"_Penalty", ""), (r"1/3", "Final_Third"),
    (r"\+/-", "Plus_Minus"), (r"/", "_per_"), (r"-", "_minus_"), (r"90s", "Mins_Per_90"),
    (r"__", "_"),
]


def clean_match_advanced_stats_data(df: pd.DataFrame) -> pd.DataFrame:
    """``.clean_match_advanced_stats_data``."""
    names = _apply(_joined(df), _MATCH_ADV)
    out = df.iloc[1:].copy()
    out.columns = names
    out = out.reset_index(drop=True)
    if any("Nation" in c for c in out.columns) and "Nation" in out.columns:
        out["Nation"] = out["Nation"].astype(object).map(
            lambda v: re.sub(r"^.*? ", "", v) if isinstance(v, str) else v
        )
    return numeric_cols(out, ["Player", "Nation", "Pos", "Age"])


_TABLE_NAMES = [
    (r"\..[0-9]", ""), (r"\.[0-9]", ""), (r"\.", "_"), (r"_Var", ""), (r"#", "Num_"),
    (r"%", "_percent"), (r"_Penalty", ""), (r"1/3", "Final_Third"), (r"\+/-", "Plus_Minus"),
    (r"/", "_per_"), (r"-", "_minus_"), (r"90s", "Mins_Per_90"), (r"__", "_"),
]


def clean_table_names(df: pd.DataFrame) -> pd.DataFrame:
    """``.clean_table_names``."""
    names = [re.sub(r"_$", "", n) for n in _apply(_joined(df), _TABLE_NAMES)]
    out = df.iloc[1:].copy()
    out.columns = names
    return out.reset_index(drop=True)


# ----------------------------------------------------------------------------
# Transfermarkt
# ----------------------------------------------------------------------------

def convert_value_to_numeric(euro_value):
    """``.convert_value_to_numeric``: '€12.50m' -> 12500000."""
    if euro_value is None or (isinstance(euro_value, float) and np.isnan(euro_value)):
        return np.nan
    clean = re.sub(r"[^\x20-\x7E]", "", str(euro_value)).lower()
    try:
        if "free" in clean:
            return 0.0
        if "loan fee" in clean:
            return convert_value_to_numeric(clean.replace("loan fee:", ""))
        if "m" in clean:
            return float(clean.replace("m", "")) * 1_000_000
        if re.search(r"th.", clean):
            return float(re.sub(r"th.", "", clean)) * 1000
        if "k" in clean:
            return float(clean.replace("k", "")) * 1000
        return float(clean)
    except ValueError:
        return np.nan


def convert_soccerdonna_value_to_numeric(euro_value):
    if euro_value is None or (isinstance(euro_value, float) and np.isnan(euro_value)):
        return np.nan
    clean = re.sub(r"[^\x20-\x7E]", "", str(euro_value)).lower().strip().replace(".", "")
    return convert_value_to_numeric(clean)


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _parse_mdy(month, day, year):
    m = _MONTHS.get(str(month)[:3].lower())
    if m is None:
        try:
            m = int(month)
        except ValueError:
            return None
    try:
        return datetime(int(year), m, int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def tm_fix_dates(dirty_dates):
    """``.tm_fix_dates``: normaliza fechas de Transfermarkt a 'YYYY-MM-DD'."""

    def fix(d):
        if d is None or (isinstance(d, float) and np.isnan(d)):
            return np.nan
        d = str(d).strip()
        if "." in d:
            first = d.split(".")[0]
            parts = re.split(r"\D+", d)
            parts = [p for p in parts if p]
            try:
                if len(first) == 4 and len(parts) >= 3:
                    return datetime(int(parts[0]), int(parts[1]), int(parts[2])).strftime("%Y-%m-%d")
                if len(first) == 2 and len(parts) >= 3:
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0])).strftime("%Y-%m-%d")
            except ValueError:
                return np.nan
            return np.nan
        parts = [p.replace(",", "") for p in d.split(" ")]
        if len(parts) != 3:
            return np.nan
        res = _parse_mdy(parts[0], parts[1], parts[2])
        return res if res else np.nan

    if isinstance(dirty_dates, (list, tuple, pd.Series, np.ndarray)):
        return [fix(d) for d in dirty_dates]
    return fix(dirty_dates)


def replace_empty_na(val):
    if val is None or (hasattr(val, "__len__") and not isinstance(val, str) and len(val) == 0):
        return np.nan
    return val


def to_date(series):
    """``lubridate::ymd`` -> columna de fechas (``datetime64``)."""
    return pd.to_datetime(series, errors="coerce", format="mixed")


def janitor_clean_name(x: str) -> str:
    """Versión simple de ``janitor::make_clean_names`` para un nombre."""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode()
    s = re.sub(r"[’']", "", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s
