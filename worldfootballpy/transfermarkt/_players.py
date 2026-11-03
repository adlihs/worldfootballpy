"""Funciones de Transfermarkt a nivel de jugador.

Traducción de player_market_values.R, player_transfer_history.R,
tm_player_bio.R, tm_player_injury_history.R y tm_player_absence.R.
"""

from __future__ import annotations

import re
import numpy as np
import pandas as pd

from .. import _http
from .._utils import (
    TM,
    as_list,
    convert_value_to_numeric,
    is_na,
    janitor_clean_name,
    progress,
    squish,
    tm_fix_dates,
    to_date,
)
from ._common import (
    attr_all,
    first_attr,
    first_text,
    frame,
    full_url,
    load,
    meta_for,
    pagination,
    tbody_rows,
    text_all,
)


# ----------------------------------------------------------------------------
# valores de mercado de plantillas
# ----------------------------------------------------------------------------

def _nth_col_values(rows, idx, fn):
    out = []
    for tr in rows:
        cells = [c for c in tr if isinstance(c.tag, str) and c.tag in ("td", "th")]
        out.append(fn(cells[idx - 1]) if len(cells) >= idx else np.nan)
    return out


def _squad_market_table(team_page) -> pd.DataFrame:
    items = [it for box in team_page.cssselect("#yw1") for it in box.cssselect(".items")]
    tbody = items[0].cssselect("tbody")[0] if items and items[0].cssselect("tbody") else None
    head = [(th.text_content() or "") for it in items for th in it.cssselect("th")]
    squad = first_text(team_page, ".data-header__headline-wrapper--oswald")
    if tbody is None:
        return pd.DataFrame()

    def idx_of(label):
        hits = [i + 1 for i, h in enumerate(head) if label in h]
        return hits[0] if hits else None

    player_num = text_all(tbody, ".rn_nummer")
    player_name = text_all(tbody, ".inline-table a", squish_it=True)
    player_url = [full_url(h) for h in attr_all(tbody, ".inline-table a", "href")]
    position = text_all(tbody, ".inline-table tr + tr td", squish_it=True)
    birthday = text_all(tbody, "td:nth-child(3)")
    nationality = attr_all(tbody, ".flaggenrahmen:nth-child(1)", "title")

    def img_alt(cell):
        alts = [i.get("alt") for a in cell.cssselect("a") for i in a.cssselect("img")]
        return alts[0] if alts else np.nan

    def nth_text(i):
        return [(c.text_content() or "") for c in tbody.cssselect(f"td:nth-child({i})")]

    def nth_img(i):
        return [img_alt(c) for c in tbody.cssselect(f"td:nth-child({i})")]

    ci = idx_of("Current club")
    current_club = nth_img(ci) if ci else [np.nan]
    hi = idx_of("Height")
    height = ([pd.to_numeric(squish(t.replace(",", ".").replace("m", "")), errors="coerce") for t in nth_text(hi)]
              if hi else [np.nan])
    fi = idx_of("Foot")
    foot = nth_text(fi) if fi else [np.nan]
    ji = idx_of("Joined")
    joined = nth_text(ji) if ji else [np.nan]
    si = idx_of("Signed from")
    joined_from = nth_img(si) if si else [np.nan]
    ki = idx_of("Contract")
    contract = nth_text(ki) if ki else [np.nan]
    value = text_all(tbody, ".rechts.hauptlink")

    df = frame({
        "squad": squad,
        "player_num": player_num or [np.nan],
        "player_name": player_name or [np.nan],
        "player_url": player_url or [np.nan],
        "player_position": position or [np.nan],
        "player_birthday": birthday or [np.nan],
        "player_nationality": nationality or [np.nan],
        "current_club": current_club,
        "player_height_mtrs": height,
        "player_foot": foot,
        "date_joined": joined,
        "joined_from": joined_from,
        "contract_expiry": contract,
        "player_market_value": value or [np.nan],
    }, n=max(len(player_name), 1))
    return df


def _finish_market(df: pd.DataFrame) -> pd.DataFrame:
    df["player_market_value_euro"] = [convert_value_to_numeric(v) for v in df["player_market_value"]]
    df["date_joined"] = tm_fix_dates(df["date_joined"])
    df["contract_expiry"] = tm_fix_dates(df["contract_expiry"])
    bday = df["player_birthday"].astype(object)
    df["player_age"] = pd.to_numeric(
        bday.map(lambda v: re.sub(r"\D", "", re.sub(r"\).*", "", re.sub(r".*\(", "", v))) if isinstance(v, str) else np.nan),
        errors="coerce")
    clean_bday = bday.map(lambda v: re.sub(r"\s*\([^)]*\)", "", v).strip() if isinstance(v, str) else v)
    df["player_dob"] = pd.to_datetime(pd.Series(tm_fix_dates(clean_bday), index=df.index), errors="coerce")
    return df


def tm_each_team_player_market_val(each_team_url, time_pause=15):
    """Valores de mercado de los jugadores de un equipo (URL de Transfermarkt del club)."""
    url = each_team_url
    if "com#" in url:
        return pd.DataFrame()
    url = url.replace("startseite", "kader") + "/plus/1"
    _http.sleep(time_pause)
    page = load(url)
    comp_name = first_text(page, ".data-header__club a")
    country = first_attr(page, ".data-header__content a img", "title")
    m = re.search(r"saison_id/(\d+)", url)
    season_start_year = float(m.group(1)) if m else np.nan
    df = _squad_market_table(page)
    if len(df) == 0:
        return df
    df["comp_name"] = comp_name
    df["season_start_year"] = season_start_year
    df["country"] = country
    df = _finish_market(df)
    cols = ["comp_name", "country", "season_start_year", "squad", "player_num", "player_name", "player_position",
            "player_dob", "player_age", "player_nationality", "current_club", "player_height_mtrs", "player_foot",
            "date_joined", "joined_from", "contract_expiry", "player_market_value_euro", "player_url"]
    return df[cols]


def tm_player_market_values(country_name, start_year, league_url=np.nan):
    """Valores de mercado de todos los jugadores de una liga en una o varias temporadas.

    ``start_year`` es el año en que empieza la temporada (2024 para la 2024/25).
    Si la liga no está en la tabla de worldfootballR, pasa ``league_url``.
    """
    if is_na(league_url):
        meta = meta_for(country_name, start_year)
    else:
        try:
            lp = load(league_url)
        except Exception as e:
            raise ValueError(f"League URL(s) {league_url} not found. Please check transfermarkt.com for the correct league URL") from e
        comp_name = first_text(lp, ".data-header__headline-wrapper--oswald")
        country = first_text(lp, ".data-header__club a")
        years = [o.get("value") for s in lp.cssselect(".chzn-select") for o in s.cssselect("option")]
        meta = pd.DataFrame({
            "comp_name": comp_name, "region": np.nan, "country": country, "comp_url": league_url,
            "season_start_year": pd.to_numeric(years, errors="coerce"),
            "season_urls": [f"{league_url}/plus/?saison_id={y}" for y in years],
        })
        meta = meta[meta["season_start_year"].isin(as_list(start_year))]
        if len(meta) == 0:
            raise ValueError(f"League URL(s) {league_url} or seasons {start_year} not found.")

    frames = []
    for season_url in meta["season_urls"]:
        season_page = load(season_url)
        teams = list(dict.fromkeys(a.get("href") for a in season_page.cssselect("#yw1 .hauptlink a") if a.get("href")))
        teams = [TM + t for t in teams if "com#" not in TM + t]
        for team_url in progress(teams, "tm_player_market_values"):
            page = load(team_url.replace("startseite", "kader") + "/plus/1")
            df = _squad_market_table(page)
            if len(df) == 0:
                continue
            df.insert(0, "season_urls", season_url)
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    allp = pd.concat(frames, ignore_index=True)
    out = meta.merge(allp, on="season_urls", how="left")
    out = _finish_market(out)
    cols = ["comp_name", "region", "country", "season_start_year", "squad", "player_num", "player_name",
            "player_position", "player_dob", "player_age", "player_nationality", "current_club", "player_height_mtrs",
            "player_foot", "date_joined", "joined_from", "contract_expiry", "player_market_value_euro", "player_url"]
    return out[[c for c in cols if c in out.columns]]


# ----------------------------------------------------------------------------
# historial de transferencias
# ----------------------------------------------------------------------------

def _standardize_fee(x):
    if not isinstance(x, str):
        return np.nan
    if "free" in x:
        return "Free transfer"
    if "end of" in x:
        return "End of loan"
    if "fee" in x:
        return "Paid loan"
    if "loan" in x:
        return "Loan"
    if re.search(r"m|th.|k", x):
        return "Transfer"
    return np.nan


def _player_name(page):
    h1 = page.cssselect("h1")
    if not h1:
        return np.nan
    return squish(re.sub(r"#[0-9]+ ", "", h1[0].text_content() or ""))


def tm_player_transfer_history(player_urls, get_extra_info=True):
    """Historial de transferencias de jugadores (usa la API interna ``ceapi`` de Transfermarkt).

    Con ``get_extra_info=True`` visita cada transferencia para obtener países,
    fecha de fin de contrato y días restantes (más lento).
    """
    frames = []
    for url in progress(as_list(player_urls), "tm_player_transfer_history"):
        page = load(url)
        name = _player_name(page)
        player_id = url.rstrip("/").split("/")[-1]
        data = _http.get_json(f"{TM}/ceapi/transferHistory/list/{player_id}")
        rows = []
        for t in data.get("transfers", []):
            fee = t.get("fee")
            rows.append({
                "url": t.get("url"),
                "season": t.get("season"),
                "transfer_date": pd.to_datetime(t.get("dateUnformatted"), errors="coerce"),
                "team_from": (t.get("from") or {}).get("clubName"),
                "team_to": (t.get("to") or {}).get("clubName"),
                "market_value": convert_value_to_numeric(t.get("marketValue")),
                "transfer_value": convert_value_to_numeric(fee),
                "transfer_type": _standardize_fee(fee),
            })
        if get_extra_info:
            for r in rows:
                r.update(_transfer_extra(r))
            cols = ["season", "transfer_date", "country_from", "team_from", "country_to", "team_to",
                    "market_value", "transfer_value", "transfer_type", "contract_expiry", "days_remaining"]
        else:
            cols = ["season", "transfer_date", "team_from", "team_to", "market_value", "transfer_value", "transfer_type"]
        df = pd.DataFrame(rows, columns=["url"] + cols)
        df = df[cols]
        df.insert(0, "player_name", name)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _transfer_extra(r):
    out = {"contract_expiry": pd.NaT, "days_remaining": np.nan, "country_from": np.nan, "country_to": np.nan}
    if not r.get("url"):
        return out
    try:
        pg = load(TM + r["url"])
    except Exception:
        return out
    tables = [t for c in pg.cssselect(".large-4.columns") for t in c.cssselect("table")[:1]]
    rows = [tr for t in tables for tr in t.cssselect("tr")]
    if not rows:
        rows = [ch for t in tables for ch in t if isinstance(ch.tag, str)]
    for row in rows:
        txt = row.text_content() or ""
        if "Remaining contract duration" in txt:
            bold = [b.text_content() for b in row.cssselect("b")]
            if bold:
                cleaned = squish(txt.replace(bold[0], ""))
                inner = re.sub(r".*\((.*)\).*", r"\1", cleaned)
                exp = pd.to_datetime(tm_fix_dates(inner), errors="coerce")
                out["contract_expiry"] = exp
                if not pd.isna(exp) and not pd.isna(r.get("transfer_date")):
                    out["days_remaining"] = float((exp - r["transfer_date"]).days)
            break
    to = [f.get("title") for c in pg.cssselect(".large-4.columns") for f in c.cssselect("table .rechts .flaggenrahmen")]
    countries = [f.get("title") for c in pg.cssselect(".large-4.columns") for f in c.cssselect("table .flaggenrahmen")]
    country_to = to[0] if to else np.nan
    if len(countries) < 2:
        country_from = countries[0] if (is_na(country_to) and countries) else np.nan
    else:
        country_from = countries[0]
    out["country_to"] = country_to
    out["country_from"] = country_from
    return out


# ----------------------------------------------------------------------------
# biografía
# ----------------------------------------------------------------------------

def tm_player_bio(player_urls):
    """Biografía de jugadores: nacimiento, nacionalidad, altura, pie, agente, contrato, valor, redes."""
    records = []
    for url in progress(as_list(player_urls), "tm_player_bio"):
        try:
            page = load(url)
        except Exception:
            continue
        name = squish(re.sub(r"#[0-9]+ ", "", " ".join(text_all(page, "div h1"))))
        m = re.search(r"(?<=spieler/)\d+", url)
        player_id = float(m.group(0)) if m else np.nan
        picture = first_attr(page, ".data-header__profile-container img.data-header__profile-image", "src")
        x1 = text_all(page, ".info-table__content--regular", squish_it=True)
        x2 = text_all(page, ".info-table__content--bold", squish_it=True)
        pairs = []
        for k, v in zip(x1, x2):
            if "Social-Media" in k:
                continue
            pairs.append((k.replace(":", ""), v))
        for a in [a for s in page.cssselect(".socialmedia-icons") for a in s.cssselect("a")]:
            pairs.append((a.get("title") or "Website", a.get("href")))
        pairs = [("Website" if k == "" else k, v) for k, v in pairs]
        seen = {}
        for k, v in pairs:
            seen.setdefault(k, v)
        val = text_all(page, ".data-header__market-value-wrapper", squish_it=True)
        seen["player_valuation"] = re.sub(r" Last.*", "", val[0]) if val else np.nan
        mx = text_all(page, ".max", squish_it=True)
        seen["max_player_valuation"] = mx[0] if mx else np.nan
        mxd = text_all(page, ".tm-player-market-value-development__max div", squish_it=True)
        seen["max_player_valuation_date"] = mxd[2] if len(mxd) > 2 else np.nan
        try:
            sn_page = load(url.replace("profil", "rueckennummern"))
            sn = sn_page.cssselect("tbody tr:first-child td:nth-child(4)")
            squad_number = sn[0].text_content().strip() if sn else np.nan
        except Exception:
            squad_number = np.nan

        rec = {"player_name": name, "player_id": player_id}
        for k, v in seen.items():
            rec[k] = v
        rec = {_clean_key(k): v for k, v in rec.items()}
        rec["squad_number"] = squad_number
        rec["player_valuation"] = convert_value_to_numeric(rec.get("player_valuation"))
        rec["max_player_valuation"] = convert_value_to_numeric(rec.get("max_player_valuation"))
        rec["max_player_valuation_date"] = tm_fix_dates(rec.get("max_player_valuation_date"))
        rec["URL"] = url
        rec["picture_url"] = picture
        rec.pop("na", None)
        records.append(rec)
    bios = pd.DataFrame(records)
    if len(bios) == 0:
        return bios
    dob_cols = [c for c in bios.columns if "date_of_birth" in c]
    if dob_cols:
        c = dob_cols[0]
        bios["date_of_birth"] = tm_fix_dates(bios[c].map(lambda v: re.sub(r" \(.*", "", v) if isinstance(v, str) else v))
        if c != "date_of_birth":
            bios = bios.drop(columns=[c])
    for c in ("joined", "contract_expires", "date_of_last_contract_extension"):
        if c in bios.columns:
            bios[c] = tm_fix_dates(bios[c])
    if "height" in bios.columns:
        bios["height"] = pd.to_numeric(
            bios["height"].map(lambda v: squish(v.replace(",", ".").replace("m", "")) if isinstance(v, str) else v),
            errors="coerce")
    return bios


def _clean_key(k):
    if k in ("player_name", "player_id", "player_valuation", "max_player_valuation", "max_player_valuation_date"):
        return k
    return janitor_clean_name(k) or "na"


# ----------------------------------------------------------------------------
# lesiones y ausencias
# ----------------------------------------------------------------------------

def tm_player_injury_history(player_urls):
    """Historial de lesiones de jugadores (temporada, lesión, fechas, días y partidos perdidos)."""
    frames = []
    for url in progress(as_list(player_urls), "tm_player_injury_history"):
        try:
            fixed = url.replace("profil", "verletzungen") + "/plus/1"
            first = load(fixed)
            name = _player_name(first)
            pages = [TM + p for p in pagination(first)] or [fixed]
            for i, pu in enumerate(pages):
                pg = first if (pu == fixed or (i == 0 and not pagination(first))) else load(pu)
                for tr in tbody_rows(pg):
                    frames.append(_injury_row(tr, name, url))
        except Exception as e:
            print(f"Error en {url}: {e}")
    if not frames:
        return pd.DataFrame()
    df = pd.DataFrame(frames)
    df["injured_since"] = to_date(df["injured_since"])
    df["injured_until"] = to_date(df["injured_until"])
    return df


def _injury_row(tr, name, url):
    def first(css, fn=lambda n: n.text_content()):
        n = tr.cssselect(css)
        return fn(n[0]) if n else np.nan

    gm = first(".wappen_verletzung")
    clubs = [i.get("alt") for i in tr.cssselect("img")]
    return {
        "player_name": name,
        "player_url": url,
        "season_injured": first("td:nth-child(1)"),
        "injury": first(".zentriert + .hauptlink"),
        "injured_since": tm_fix_dates(first(".hauptlink + .zentriert")),
        "injured_until": tm_fix_dates(first(".zentriert + td.zentriert")),
        "duration": first(".zentriert + td.rechts"),
        "games_missed": (str(int(float(gm))) if isinstance(gm, str) and re.fullmatch(r"\s*\d+\s*", gm) else np.nan),
        "club_missed_games_for": ", ".join(c for c in clubs if c) if clubs else "NA",
    }


def _absence_page(url):
    pg = load(url)
    items = pg.cssselect("#yw1 .items")
    if not items:
        return pd.DataFrame()
    from .._table import html_table

    main = html_table(items[0])
    if len(main) == 0:
        return main
    rows = items[0].cssselect("tbody tr")
    head = [(th.text_content() or "").lower() for th in items[0].cssselect("tr th")]
    comp_idx = next((i for i, h in enumerate(head) if "competition" in h), None)
    club_idx = next((i for i, h in enumerate(head) if "games missed" in h), None)

    def pick(tr, idx, css, attr):
        tds = tr.cssselect("td")
        if idx is None or len(tds) <= idx:
            return np.nan
        vals = [n.get(attr) for n in tds[idx].cssselect(css)]
        return vals[0] if vals else np.nan

    main = main.iloc[: len(rows)].copy()
    main["Competition"] = [pick(tr, comp_idx, "img", "title") for tr in rows][: len(main)]
    main["club_missed"] = [pick(tr, club_idx, "a", "title") for tr in rows][: len(main)]
    main = main.astype(object).where(main.notna(), np.nan)
    main = main.apply(lambda col: col.map(lambda v: v if (isinstance(v, str) or is_na(v)) else str(v)))
    for c in ("from", "until"):
        if c in main.columns:
            main[c] = tm_fix_dates(main[c])
    main.columns = [janitor_clean_name(c) for c in main.columns]
    return main


def tm_get_player_absence(player_urls):
    """Ausencias de jugadores (lesiones, sanciones, otros motivos) con partidos perdidos."""
    frames = []
    for url in progress(as_list(player_urls), "tm_get_player_absence"):
        try:
            changed = url.replace("profil", "ausfaelle")
            pg = load(changed)
            name = _player_name(pg)
            pages = [TM + p for p in pagination(pg)] or [changed]
            parts = []
            for p in pages:
                try:
                    parts.append(_absence_page(p))
                except Exception as e:
                    print(f"Error en {p}: {e}")
            body = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame()
            if len(body) == 0:
                body = pd.DataFrame(index=[0])
            body.insert(0, "player_url", url)
            body.insert(0, "player_name", name)
            frames.append(body)
        except Exception as e:
            print(f"Error en {url}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


__all__ = ["tm_each_team_player_market_val", "tm_player_market_values", "tm_player_transfer_history",
           "tm_player_bio", "tm_player_injury_history", "tm_get_player_absence"]
