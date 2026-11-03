"""Funciones de Transfermarkt a nivel de liga.

Traducción de tm_league_team_urls/tm_team_player_urls/tm_team_staff_urls
(worldfootballr_helpers.R), tm_expiring_contracts.R, tm_league_debutants.R,
tm_league_injuries.R, tm_league_suspensions.R, tm_matchday_table.R y
tm_team_transfer_balances.R.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .._table import html_table
from .._utils import (
    TM,
    as_list,
    convert_value_to_numeric,
    is_na,
    progress,
    squish,
    tm_fix_dates,
    to_date,
)
from ._common import (
    attr_all,
    first_text,
    frame,
    full_url,
    league_header,
    load,
    meta_for,
    pagination,
    tbody_rows,
    text_all,
)


# ----------------------------------------------------------------------------
# URLs
# ----------------------------------------------------------------------------

def tm_league_team_urls(country_name, start_year, league_url=np.nan):
    """URLs de los equipos de una liga y temporada (``start_year`` = año de inicio)."""
    if is_na(league_url):
        season_url = meta_for(country_name, start_year)["season_urls"].iloc[0]
    else:
        try:
            load(league_url)
        except Exception as e:
            raise ValueError(f"League URL(s) {league_url} not found. Please check transfermarkt.com for the correct league URL") from e
        season_url = f"{league_url}?saison_id={start_year}"
    page = load(season_url)
    hrefs = list(dict.fromkeys(a.get("href") for a in page.cssselect("#yw1 .hauptlink a") if a.get("href")))
    urls = [TM + h for h in hrefs]
    return [u for u in urls if ".com#" not in u]


def tm_team_player_urls(team_url):
    """URLs de los jugadores de la plantilla de un equipo."""
    page = load(team_url)
    hrefs = list(dict.fromkeys(a.get("href") for a in page.cssselect("#yw1 td.posrela .hauptlink a") if a.get("href")))
    return [TM + h for h in hrefs]


_STAFF_ROLES = ["Manager", "Assistant Manager", "Goalkeeping Coach", "Fitness Coach", "Conditioning Coach"]


def tm_team_staff_urls(team_urls, staff_role):
    """URLs del cuerpo técnico de equipos para un rol (``"Manager"``, ``"Assistant Manager"``,
    ``"Goalkeeping Coach"``, ``"Fitness Coach"``, ``"Conditioning Coach"``)."""
    if staff_role not in _STAFF_ROLES:
        raise ValueError("Check that staff role is one of:\n'Manager', 'Assistant Manager', "
                         "'Goalkeeping Coach', 'Fitness Coach' or 'Conditioning Coach'")
    out = []
    for team_url in progress(as_list(team_urls), "tm_team_staff_urls"):
        try:
            url = re.sub(r"/saison_id.*", "", team_url.replace("startseite", "mitarbeiter"))
            pg = load(url)
            boxes = [b for c in pg.cssselect(".large-8") for b in c.cssselect(".box")]
            if not boxes:
                out.append(np.nan)
                continue
            box = boxes[0]
            names = box.cssselect(".hauptlink a")
            urls = [TM + (a.get("href") or "") for a in names]
            positions = text_all(box, ".inline-table tr + tr td")
            df = frame({"url": urls, "position": positions})
            wanted = ["Manager", "Caretaker Manager"] if staff_role == "Manager" else [staff_role]
            out.extend(df[df["position"].isin(wanted)]["url"].tolist())
        except Exception as e:
            print(f"Error en {team_url}: {e}")
            out.append(np.nan)
    return out


# ----------------------------------------------------------------------------
# helpers de liga
# ----------------------------------------------------------------------------

def _resolve_league(country_name, league_url):
    """Devuelve (comp_url, meta_cols) con comp_name/country/comp_url."""
    if is_na(league_url):
        meta = meta_for(country_name)
        comp_url = meta["comp_url"].dropna().unique()[0]
        info = meta[["comp_name", "country", "comp_url"]].drop_duplicates().iloc[0].to_dict()
    else:
        try:
            page = load(league_url)
        except Exception as e:
            raise ValueError(f"League URL(s) {league_url} not found. Please check transfermarkt.com for the correct league URL") from e
        country, comp_name = league_header(page)
        comp_url = league_url
        info = {"comp_name": comp_name, "country": country, "comp_url": league_url}
    return comp_url, info


def _second_nationality(rows):
    out = []
    for tr in rows:
        nats = [n.get("title") for n in tr.cssselect("br + .flaggenrahmen")]
        out.append(nats[0] if nats else np.nan)
    return out


def _with_info(df, info):
    for i, (k, v) in enumerate(info.items()):
        df.insert(i, k, v)
    return df


# ----------------------------------------------------------------------------
# contratos que expiran
# ----------------------------------------------------------------------------

def tm_expiring_contracts(country_name, contract_end_year, league_url=np.nan):
    """Jugadores de una liga cuyo contrato termina en ``contract_end_year``."""
    comp_url, info = _resolve_league(country_name, league_url)
    comp_url = comp_url.replace("startseite", "endendevertraege")
    comp_url += (f"/plus/1/galerie/0?jahr={contract_end_year}&ausrichtung=alle&spielerposition_id=alle"
                 "&altersklasse=alle&land_id=0&yt0=Show")
    first = load(comp_url)
    pages = [TM + p for p in pagination(first)] or [comp_url]
    frames = []
    for pu in pages:
        try:
            rows = tbody_rows(load(pu) if pu != comp_url else first)
            if not rows:
                continue
            body = _RowsView(rows)
            df = frame({
                "player_name": body.texts(".inline-table .hauptlink a"),
                "player_url": [full_url(h) for h in body.attrs(".inline-table .hauptlink a", "href")],
                "date_of_birth": body.texts("td.zentriert:nth-child(2)"),
                "position": body.texts(".inline-table tr + tr td"),
                "nationality": body.attrs(".flaggenrahmen:nth-child(1)", "title"),
                "second_nationality": _second_nationality(rows),
                "current_club": body.attrs(".tiny_wappen", "alt"),
                "contract_expiry": tm_fix_dates(body.texts(".no-border-rechts + .zentriert")),
                "contract_option": body.texts(".no-border-rechts ~ .zentriert + .zentriert"),
                "player_market_value": [convert_value_to_numeric(v) for v in body.texts(".zentriert + .hauptlink")],
                "transfer_fee": [convert_value_to_numeric(v) for v in body.texts(".hauptlink + .rechts")],
                "agent": [squish(v) for v in body.texts(".rechts + .hauptlink")],
            }, n=len(body.texts(".inline-table .hauptlink a")))
            df["contract_expiry"] = to_date(df["contract_expiry"])
            frames.append(_with_info(df, info))
        except Exception as e:
            print(f"Error en {pu}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


class _RowsView:
    """Aplica selectores CSS a un conjunto de filas (como rvest sobre un nodeset)."""

    def __init__(self, rows):
        self.rows = rows

    def nodes(self, css):
        return [n for r in self.rows for n in r.cssselect(css)]

    def texts(self, css):
        return [(n.text_content() or "") for n in self.nodes(css)]

    def attrs(self, css, name):
        return [n.get(name) for n in self.nodes(css)]


# ----------------------------------------------------------------------------
# debutantes
# ----------------------------------------------------------------------------

def tm_league_debutants(country_name, league_url=np.nan, debut_type="league", debut_start_year=None,
                        debut_end_year=None):
    """Jugadores que debutaron en la liga (``debut_type="league"``) o como profesionales (``"pro"``)."""
    comp_url, info = _resolve_league(country_name, league_url)
    comp_url = comp_url.replace("startseite", "profidebuetanten")
    comp_url += f"/plus/1/galerie/0?saisonIdVon={debut_start_year}&saison_id={debut_end_year}&option="
    if debut_type == "league":
        comp_url += "liga"
    elif debut_type == "pro":
        comp_url += "profi"
    else:
        raise ValueError("Check debut type is either 'league' or 'pro'")
    first = load(comp_url)
    pages = [TM + p for p in pagination(first)] or [comp_url]
    frames = []
    for pu in pages:
        try:
            rows = tbody_rows(first if pu == comp_url else load(pu))
            b = _RowsView(rows)
            names = b.texts(".inline-table .hauptlink a")
            debut_for = b.attrs(".zentriert + .zentriert img", "alt")
            home = b.attrs(".rechts img", "alt")
            away = b.attrs(".links img", "alt")
            score = b.texts(".ergebnis-link span")
            hg = [pd.to_numeric(re.sub(r":.*", "", s), errors="coerce") for s in score]
            ag = [pd.to_numeric(re.sub(r".*:", "", s), errors="coerce") for s in score]
            n = len(names)

            def at(lst, i):
                return lst[i] if i < len(lst) else np.nan

            opponent = [at(away, i) if at(debut_for, i) == at(home, i) else at(home, i) for i in range(n)]
            gf = [at(hg, i) if at(debut_for, i) == at(home, i) else at(ag, i) for i in range(n)]
            ga = [at(ag, i) if at(debut_for, i) == at(home, i) else at(hg, i) for i in range(n)]
            df = frame({
                "player_name": names,
                "player_url": [full_url(h) for h in b.attrs(".inline-table .hauptlink a", "href")],
                "position": b.texts(".inline-table tr + tr td"),
                "nationality": b.attrs(".flaggenrahmen:nth-child(1)", "title"),
                "second_nationality": _second_nationality(rows),
                "debut_for": debut_for,
                "debut_date": tm_fix_dates(b.texts(".spielDatum")),
                "opponent": opponent,
                "goals_for": gf,
                "goals_against": ga,
                "age_debut": [squish(v) for v in b.texts(".match + .hauptlink")],
                "value_at_debut": [convert_value_to_numeric(v) for v in b.texts(".hauptlink:nth-child(9)")],
                "player_market_value": [convert_value_to_numeric(v) for v in
                                        b.texts(".rechts.hauptlink ~ .hauptlink + .hauptlink")],
                "appearances": [pd.to_numeric(re.sub(r"Not.*", "0", v), errors="coerce")
                                for v in b.texts(".zentriert.hauptlink a")],
                "goals": [pd.to_numeric(v.replace("-", "0"), errors="coerce") for v in b.texts(".hauptlink + .zentriert a")],
                "minutes_played": [pd.to_numeric(v.replace(".", "").replace("'", "").replace("-", "0"), errors="coerce")
                                   for v in b.texts("td:nth-child(6)")],
            }, n=n)
            df["debut_date"] = to_date(df["debut_date"])
            df = _with_info(df, info)
            df["debut_type"] = debut_type
            frames.append(df)
        except Exception as e:
            print(f"Error en {pu}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# lesionados actuales de la liga
# ----------------------------------------------------------------------------

def tm_league_injuries(country_name, league_url=np.nan):
    """Jugadores lesionados actualmente en una liga."""
    comp_url, info = _resolve_league(country_name, league_url)
    page = load(comp_url.replace("startseite", "verletztespieler") + "/plus/1")
    rows = tbody_rows(page)
    b = _RowsView(rows)
    names = b.texts(".inline-table .hauptlink a")
    df = frame({
        "player_name": names,
        "player_url": [full_url(h) for h in b.attrs(".inline-table .hauptlink a", "href")],
        "position": b.texts(".inline-table tr + tr td"),
        "current_club": b.attrs(".tiny_wappen", "alt"),
        "age": [pd.to_numeric(v, errors="coerce") for v in b.texts(".no-border-rechts + .zentriert")],
        "nationality": b.attrs(".flaggenrahmen:nth-child(1)", "title"),
        "second_nationality": _second_nationality(rows),
        "injury": b.texts("td.links"),
        "injured_since": tm_fix_dates(b.texts(".links + td")),
        "injured_until": tm_fix_dates(b.texts(".links ~ .zentriert + td.zentriert")),
        "player_market_value": [convert_value_to_numeric(v) for v in b.texts("td.rechts")],
    }, n=len(names))
    df["injured_since"] = to_date(df["injured_since"])
    df["injured_until"] = to_date(df["injured_until"])
    return _with_info(df, info)


# ----------------------------------------------------------------------------
# sanciones
# ----------------------------------------------------------------------------

def _suspension_source(country_name, league_url):
    if is_na(league_url):
        if is_na(country_name):
            raise ValueError("You must provide either league_url or country_name")
        meta = meta_for(country_name)
        return meta["comp_url"].iloc[0], meta["comp_name"].iloc[0], country_name
    page = load(league_url)
    comp_name = first_text(page, ".data-header__headline-wrapper--oswald")
    imgs = attr_all(page, ".data-header img", "alt")
    country = squish(imgs[0]) if imgs and imgs[0] else np.nan
    return league_url, comp_name, country


def _cell(tr, css, attr=None):
    n = tr.cssselect(css)
    if not n:
        return np.nan
    v = n[0].get(attr) if attr else n[0].text_content()
    if v is None:
        return np.nan
    v = v.strip()
    return v if v != "" else np.nan


def _suspension_rows(comp_url, box_idx):
    page = load(comp_url.replace("startseite", "sperrenausfaelle") + "/plus/1")
    boxes = page.cssselect("div.box")
    if len(boxes) <= box_idx:
        return []
    tables = boxes[box_idx].cssselect("table.items")
    if not tables:
        return []
    return [tr for tr in tables[0].cssselect("tbody tr") if tr.cssselect("table.inline-table")]


def tm_get_suspensions(country_name=np.nan, league_url=np.nan):
    """Jugadores sancionados actualmente en una liga (motivo, desde, hasta, partidos)."""
    comp_url, comp_name, country = _suspension_source(country_name, league_url)
    recs = []
    for tr in _suspension_rows(comp_url, 0):
        info = tr.cssselect("td:first-child table.inline-table")
        info = info[0] if info else tr
        since = _cell(tr, "td:nth-child(5)")
        until = _cell(tr, "td:nth-child(6)")
        recs.append({
            "Player": _cell(info, "td:nth-child(2) a"),
            "Position": _cell(info, "tr:nth-child(2) td"),
            "Club": _cell(tr, "td:nth-child(2) a img", "title"),
            "Age": pd.to_numeric(_cell(tr, "td:nth-child(3)"), errors="coerce"),
            "Reason": _cell(tr, "td:nth-child(4)"),
            "Since": pd.to_datetime(tm_fix_dates(since), errors="coerce"),
            "Until": pd.to_datetime(tm_fix_dates(until), errors="coerce"),
            "Matches_Missed": pd.to_numeric(_cell(tr, "td:nth-child(7)"), errors="coerce"),
        })
    df = pd.DataFrame(recs)
    if len(df):
        df.insert(0, "Competition", comp_name)
        df.insert(0, "Country", country)
    return df


def tm_get_risk_of_suspension(country_name=np.nan, league_url=np.nan):
    """Jugadores en riesgo de sanción por acumulación de amarillas."""
    comp_url, comp_name, country = _suspension_source(country_name, league_url)
    recs = []
    for tr in _suspension_rows(comp_url, 1):
        info = tr.cssselect("td:first-child table.inline-table")
        info = info[0] if info else tr
        recs.append({
            "Player": _cell(info, "td:nth-child(2) a"),
            "Position": _cell(info, "tr:nth-child(2) td"),
            "Club": _cell(tr, "td:nth-child(2) a img", "title"),
            "Age": pd.to_numeric(_cell(tr, "td:nth-child(3)"), errors="coerce"),
            "Yellow_Cards": pd.to_numeric(_cell(tr, "td:nth-child(4)"), errors="coerce"),
        })
    df = pd.DataFrame(recs, columns=["Player", "Position", "Club", "Age", "Yellow_Cards"])
    df.insert(0, "Competition", comp_name)
    df.insert(0, "Country", country)
    return df


# ----------------------------------------------------------------------------
# tabla por jornada
# ----------------------------------------------------------------------------

def tm_matchday_table(country_name, start_year, matchday, league_url=np.nan):
    """Tabla de posiciones de la liga tras cada jornada indicada en ``matchday``."""
    if is_na(league_url):
        season_url = meta_for(country_name, start_year)["season_urls"].iloc[0]
    else:
        lp = load(league_url)
        country_name, _ = league_header(lp)
        season_url = league_url
    season_url = season_url.replace("startseite", "spieltagtabelle")
    frames = []
    for md in as_list(matchday):
        if is_na(league_url):
            url = f"{season_url}&spieltag={md}"
        else:
            url = f"{season_url}?saison_id={start_year}&spieltag={md}"
        tab = load(url)
        h1 = tab.cssselect("h1")
        league_name = squish(h1[0].text_content()) if h1 else np.nan
        boxes = tab.cssselect(".box")[1:]
        idx = [i for i, b in enumerate(boxes) if len(b.cssselect("th")) == 9]
        parts = [html_table(boxes[i].cssselect("table")[0]) for i in idx[:2]]
        if not parts:
            continue
        t = pd.concat(parts, ignore_index=True)
        cols = list(t.columns)
        # columnas: '#', club(escudo), 'Club'(nombre), 'Var.4'(P), W, D, L, Goals, '+/-', Pts
        out = pd.DataFrame({
            "country": country_name,
            "league": league_name,
            "matchday": md,
            "rk": t[cols[0]],
            "squad": t["Club.1"] if "Club.1" in t.columns else t[cols[2]],
            "p": pd.to_numeric(t["Var.4"] if "Var.4" in t.columns else t[cols[3]], errors="coerce"),
            "w": pd.to_numeric(t["W"], errors="coerce"),
            "d": pd.to_numeric(t["D"], errors="coerce"),
            "l": pd.to_numeric(t["L"], errors="coerce"),
        })
        goals = t["Goals"].astype(str).str.split(":", n=1, expand=True)
        out["gf"] = pd.to_numeric(goals[0], errors="coerce")
        out["ga"] = pd.to_numeric(goals[1] if goals.shape[1] > 1 else np.nan, errors="coerce")
        gd_col = [c for c in cols if c in ("X...", "X..", "+/-")] or [cols[-2]]
        out["g_diff"] = pd.to_numeric(t[gd_col[0]], errors="coerce")
        out["pts"] = pd.to_numeric(t["Pts"], errors="coerce")
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# balance de transferencias por equipo
# ----------------------------------------------------------------------------

def tm_team_transfer_balances(country_name, start_year, league_url=np.nan):
    """Gasto, ingreso y edad media de llegadas/salidas de cada equipo de una liga en una temporada."""
    if is_na(league_url):
        season_url = meta_for(country_name, start_year)["season_urls"].iloc[0]
    else:
        load(league_url)
        season_url = f"{league_url}?saison_id={start_year}"
    page = load(season_url.replace("startseite", "transfers"))
    boxes = [b for c in page.cssselect(".large-8") for b in c.cssselect(".box")]

    def team_link(b):
        a = b.cssselect("a + a")
        return (a[0].text_content() or "") if a else None

    boxes = [b for b in boxes if team_link(b) is not None]
    country, league_name = league_header(page)
    season = np.nan
    if boxes:
        hl = boxes[0].cssselect(".content-box-headline")
        if hl:
            season = squish(hl[0].text_content()).replace("Transfers ", "")
    recs = []
    for b in boxes:
        team = team_link(b)
        if not team or "Transfer" in team:
            continue
        vals = [squish(v) for v in text_all(b, ".transfer-einnahmen-ausgaben")]
        ages = [squish(v) for v in text_all(b, ".transfer-zusatzinfo-alter")]
        recs.append({
            "country": country, "league": league_name, "season": season, "squad": team,
            "expenditure_euros": vals[0] if vals else np.nan,
            "income_euros": vals[1] if len(vals) > 1 else np.nan,
            "avg_age_out": ages[1] if len(ages) > 1 else np.nan,
            "avg_age_in": ages[0] if ages else np.nan,
        })
    df = pd.DataFrame(recs)
    if len(df) == 0:
        return df
    df["expenditure_euros"] = [convert_value_to_numeric(str(v).replace("Expenditure: ", "")) for v in df["expenditure_euros"]]
    df["income_euros"] = [convert_value_to_numeric(str(v).replace("Income: ", "")) for v in df["income_euros"]]
    for c in ("avg_age_out", "avg_age_in"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r".*:", "", regex=True), errors="coerce")
    return df


__all__ = ["tm_league_team_urls", "tm_team_player_urls", "tm_team_staff_urls", "tm_expiring_contracts",
           "tm_league_debutants", "tm_league_injuries", "tm_get_suspensions", "tm_get_risk_of_suspension",
           "tm_matchday_table", "tm_team_transfer_balances"]
