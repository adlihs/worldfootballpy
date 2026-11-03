"""Utilidades compartidas para Transfermarkt."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import _http
from .._utils import DATA_REPO_RAW, TM, as_list, squish

TM_LEAGUES_CSV = f"{DATA_REPO_RAW}/raw-data/transfermarkt_leagues/main_comp_seasons.csv"
TM_STAFF_CSV = f"{DATA_REPO_RAW}/raw-data/transfermarkt_staff/tm_staff_types.csv"


def tm_meta() -> pd.DataFrame:
    """Tabla de ligas/temporadas de Transfermarkt (worldfootballR_data)."""
    return _http.read_csv_url(TM_LEAGUES_CSV)


def meta_for(country_name, start_year=None):
    meta = tm_meta()
    df = meta[meta["country"].isin(as_list(country_name))]
    if start_year is not None:
        df = df[df["season_start_year"].isin(as_list(start_year))]
    if len(df) == 0:
        what = f"Country {country_name}" + (f" or season {start_year}" if start_year is not None else "")
        raise ValueError(
            f"{what} not found. Check that the country and season exists at "
            "https://github.com/JaseZiv/worldfootballR_data/blob/master/raw-data/transfermarkt_leagues/main_comp_seasons.csv"
        )
    return df


def load(url):
    return _http.load_page(url)


def text_all(el, css, squish_it=False):
    out = [(n.text_content() or "") for n in el.cssselect(css)]
    return [squish(t) for t in out] if squish_it else out


def attr_all(el, css, name):
    return [n.get(name) for n in el.cssselect(css)]


def first_text(el, css, squish_it=True):
    t = text_all(el, css, squish_it)
    return t[0] if t else np.nan


def first_attr(el, css, name):
    a = attr_all(el, css, name)
    return a[0] if a and a[0] is not None else np.nan


def tbody_rows(page, css="#yw1"):
    """``html_nodes(css) %>% html_nodes("tbody") %>% .[[1]] %>% html_children()``."""
    for box in page.cssselect(css):
        tb = box.cssselect("tbody")
        if tb:
            return [c for c in tb[0] if isinstance(c.tag, str)]
    return []


def frame(columns: dict, n=None) -> pd.DataFrame:
    """``cbind(...) %>% data.frame()``: rellena con NA las columnas más cortas."""
    lengths = [len(v) for v in columns.values() if isinstance(v, (list, tuple, np.ndarray, pd.Series))]
    n = n if n is not None else (max(lengths) if lengths else 1)
    out = {}
    for k, v in columns.items():
        if isinstance(v, (list, tuple, np.ndarray, pd.Series)):
            v = list(v)
            if len(v) == 1 and n > 1:
                v = v * n
            v = (v + [np.nan] * n)[:n]
        else:
            v = [v] * n
        out[k] = v
    return pd.DataFrame(out)


def league_header(page):
    """País y nombre de la competición desde la cabecera de una página de liga."""
    country = np.nan
    for h in page.cssselect(".data-header"):
        imgs = h.cssselect("img")
        if imgs and imgs[0].get("alt"):
            country = squish(imgs[0].get("alt"))
            break
    comp_name = first_text(page, ".data-header__headline-wrapper--oswald")
    return country, comp_name


def full_url(href):
    return TM + href if isinstance(href, str) else np.nan


def pagination(page):
    return list(dict.fromkeys(a.get("href") for a in page.cssselect(".tm-pagination__list-item a") if a.get("href")))
