"""Acceso HTTP compartido por todas las fuentes.

Equivalente a ``.load_page()``, ``.get_understat_json()`` y ``.file_reader()``
de worldfootballR.
"""

from __future__ import annotations

import io
import time
import warnings
from functools import lru_cache

import lxml.html
import pandas as pd
import requests

_DEFAULT_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 worldfootballpy"
)

_config = {"user_agent": _DEFAULT_AGENT, "timeout": 60}
_session = requests.Session()


def set_user_agent(agent: str) -> None:
    """Cambia el User-Agent usado en todas las peticiones.

    Equivale a ``options(worldfootballR.agent = ...)`` en R.
    """
    _config["user_agent"] = agent


def get_user_agent() -> str:
    return _config["user_agent"]


def _headers() -> dict:
    return {"User-Agent": _config["user_agent"], "Accept-Language": "en-US,en;q=0.9"}


def sleep(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


def get(url: str, **kwargs) -> requests.Response:
    headers = {**_headers(), **kwargs.pop("headers", {})}
    resp = _session.get(url, headers=headers, timeout=_config["timeout"], **kwargs)
    resp.raise_for_status()
    return resp


def load_page(url: str, **kwargs):
    """Descarga una página y la devuelve como árbol lxml (como ``xml2::read_html``)."""
    resp = get(url, **kwargs)
    return parse_html(resp.content)


def parse_html(content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return lxml.html.fromstring(content)


def get_json(url: str, **kwargs):
    return get(url, **kwargs).json()


@lru_cache(maxsize=32)
def _read_csv_cached(url: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(get(url).content))


def read_csv_url(url: str) -> pd.DataFrame:
    """Lee un CSV remoto (cacheado durante la sesión)."""
    return _read_csv_cached(url).copy()


def file_reader(url: str) -> pd.DataFrame:
    """Lee un archivo ``.rds`` publicado en GitHub (equivalente a ``.file_reader``).

    Devuelve un DataFrame vacío si el archivo no existe o no se puede leer.
    """
    try:
        import rdata
    except ImportError as e:  # pragma: no cover
        raise ImportError("Instala 'rdata' para usar las funciones load_*: pip install rdata") from e
    try:
        raw = get(url).content
    except requests.RequestException:
        return pd.DataFrame()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = rdata.parser.parse_data(raw)
            converted = rdata.conversion.convert(
                parsed, constructor_dict=_constructors(rdata), default_encoding="utf-8"
            )
    except Exception:
        return pd.DataFrame()
    if not isinstance(converted, pd.DataFrame):
        try:
            converted = pd.DataFrame(converted)
        except Exception:
            return pd.DataFrame()
    converted = converted.reset_index(drop=True)
    converted.columns = [str(c) for c in converted.columns]
    for col in converted.columns:
        if isinstance(converted[col].dtype, pd.CategoricalDtype):
            converted[col] = converted[col].astype(object)
    ts = _scrape_timestamp(parsed)
    if ts is not None:
        converted.attrs["scrape_timestamp"] = ts
    return converted


def _constructors(rdata):
    """Añade conversores para fechas de R (``Date`` y ``POSIXct``)."""
    import numpy as np

    def date_constructor(obj, attrs):
        arr = np.asarray(obj, dtype="float64")
        return pd.to_datetime(arr, unit="D", errors="coerce")

    def posixct_constructor(obj, attrs):
        arr = np.asarray(obj, dtype="float64")
        return pd.to_datetime(arr, unit="s", errors="coerce", utc=True)

    def posixt_constructor(obj, attrs):
        return obj

    d = dict(rdata.conversion.DEFAULT_CLASS_MAP)
    d.update({"Date": date_constructor, "POSIXct": posixct_constructor, "POSIXt": posixt_constructor,
              "POSIXlt": posixt_constructor})
    return d


def _scrape_timestamp(parsed):
    """Extrae el atributo ``scrape_timestamp`` (POSIXlt de R) del objeto, si existe."""
    try:
        node = parsed.object.attributes
        while node is not None:
            pair = node.value
            name = node.tag.value.value if node.tag is not None and node.tag.value is not None else None
            if isinstance(name, bytes):
                name = name.decode()
            if name == "scrape_timestamp":
                parts = [float(x.value[0]) for x in pair[0].value[:6]]
                sec, minute, hour, mday, mon, year = parts
                return pd.Timestamp(year=int(year) + 1900, month=int(mon) + 1, day=int(mday),
                                    hour=int(hour), minute=int(minute), second=int(sec), tz="UTC")
            node = pair[1] if isinstance(pair, tuple) and len(pair) > 1 else None
    except Exception:
        return None
    return None
