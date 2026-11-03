"""Funciones para Understat (https://understat.com).

Traducción de understat_*.R, load_understat.R y de las funciones internas
``.get_clean_understat_json`` y ``.understat_shooting``.

Ligas disponibles: ``"EPL"``, ``"La liga"``, ``"Bundesliga"``, ``"Serie A"``,
``"Ligue 1"``, ``"RFPL"``.
"""

from __future__ import annotations

import json
import random
import re

import numpy as np
import pandas as pd

from .. import _http
from .._utils import DATA_REPO_RELEASES, UNDERSTAT, as_list, janitor_clean_name, progress, squish

LEAGUES = {
    "EPL": "EPL",
    "La liga": "La_liga",
    "Bundesliga": "Bundesliga",
    "Serie A": "Serie_A",
    "Ligue 1": "Ligue_1",
    "RFPL": "RFPL",
}

_COOKIES = {"beget": "begetok"}

# Algunas páginas de Understat cargan los datos con peticiones AJAX en vez de
# incrustarlos en <script>. Si no se encuentra el script, se prueba este endpoint.
_AJAX = {
    "league": "getLeagueData",
    "team": "getTeamData",
    "match": "getMatchData",
    "player": "getPlayerData",
}
_AJAX_KEYS = {
    "datesData": "dates",
    "shotsData": "shots",
    "playersData": "players",
    "statisticsData": "statistics",
    "rostersData": "rosters",
    "teamsData": "teams",
}


def _check_league(league):
    if league not in LEAGUES:
        raise ValueError(f"league debe ser uno de {list(LEAGUES)}")
    return LEAGUES[league]


def _get_page(url):
    try:
        return _http.get(url, cookies=_COOKIES).text
    except Exception:
        return None


def _decode_js_string(s: str) -> str:
    s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\'", "'").replace("\\\\", "\\")


def _extract_var(html: str, var_name: str):
    m = re.search(var_name + r"\s*=\s*JSON\.parse\('(.*?)'\)", html, flags=re.S)
    if not m:
        return None
    return json.loads(_decode_js_string(m.group(1)))


def _ajax_fallback(page_url, var_name):
    m = re.match(r"https?://understat\.com/(league|team|match|player)/(.+?)/?$", page_url)
    key = _AJAX_KEYS.get(var_name)
    if not m or not key:
        return None
    kind, rest = m.groups()
    try:
        resp = _http.get(f"{UNDERSTAT}/{_AJAX[kind]}/{rest}", cookies=_COOKIES,
                         headers={"X-Requested-With": "XMLHttpRequest", "Referer": page_url})
        data = resp.json()
    except Exception:
        return None
    return data.get(key) if isinstance(data, dict) else None


def _get_var(page_url, var_name, html=None):
    html = html if html is not None else _get_page(page_url)
    data = _extract_var(html, var_name) if html else None
    if data is None:
        data = _ajax_fallback(page_url, var_name)
    return data, html


def _selected_season(html):
    if not html:
        return None
    page = _http.parse_html(html)
    opts = page.xpath('//*[@name="season"]//option[@selected]')
    return (opts[0].text_content() or "").strip() if opts else None


def _records(data):
    """Aplana el JSON como ``rm_square`` + ``rbind`` en R."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        vals = list(data.values())
        if vals and all(isinstance(v, list) for v in vals):
            return [r for v in vals for r in v]
        if vals and all(isinstance(v, dict) for v in vals):
            return vals
    return []


def _clean_json(page_url, var_name) -> pd.DataFrame:
    """``.get_clean_understat_json``."""
    data, html = _get_var(page_url, var_name)
    recs = _records(data)
    if not recs:
        return pd.DataFrame()
    df = pd.json_normalize(recs, sep=".")
    if not any("season" in c for c in df.columns):
        season = _selected_season(html)
        if season is not None:
            df.insert(0, "season", season)
    return df


def _to_num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _shooting(type_url, pause=True) -> pd.DataFrame:
    games = _clean_json(type_url, "datesData")
    if len(games) == 0:
        return pd.DataFrame()
    games = games[games["isResult"].astype(bool)]
    frames = []
    for mid in progress(games["id"].tolist(), "understat shots"):
        if pause:
            _http.sleep(round(random.uniform(1, 2)))
        url = f"{UNDERSTAT}/match/{mid}"
        try:
            df = _clean_json(url, "shotsData")
        except Exception:
            df = pd.DataFrame()
        if len(df) == 0:
            print(f"Shots data for match_url {url} not available")
            continue
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


_SHOT_RENAMES = {"h_a": "home_away", "h_team": "home_team", "a_team": "away_team",
                 "h_goals": "home_goals", "a_goals": "away_goals"}


# ----------------------------------------------------------------------------
# funciones públicas
# ----------------------------------------------------------------------------

def understat_league_match_results(league, season_start_year):
    """Resultados de los partidos (con xG y pronósticos) de una liga y temporada."""
    lg = _check_league(league)
    df = _clean_json(f"{UNDERSTAT}/league/{lg}/{season_start_year}", "datesData")
    if len(df) == 0:
        return df
    df = df[df["isResult"].astype(bool)].copy()
    df.insert(0, "league", lg)
    df = df.rename(columns={
        "id": "match_id", "h.id": "home_id", "h.title": "home_team", "h.short_title": "home_abbr",
        "a.id": "away_id", "a.title": "away_team", "a.short_title": "away_abbr",
        "goals.h": "home_goals", "goals.a": "away_goals", "xG.h": "home_xG", "xG.a": "away_xG",
        "forecast.w": "forecast_win", "forecast.d": "forecast_draw", "forecast.l": "forecast_loss",
    })
    return _to_num(df, ["home_goals", "away_goals", "home_xG", "away_xG", "forecast_win", "forecast_draw",
                        "forecast_loss"]).reset_index(drop=True)


def understat_league_season_shots(league, season_start_year):
    """Todos los tiros (con coordenadas y xG) de una liga y temporada. Es lento: visita cada partido."""
    lg = _check_league(league)
    df = _shooting(f"{UNDERSTAT}/league/{lg}/{season_start_year}")
    if len(df) == 0:
        return df
    df.insert(0, "league", lg)
    df = df.rename(columns={"h_team": "home_team", "a_team": "away_team", "h_goals": "home_goals",
                            "a_goals": "away_goals"})
    return _to_num(df, ["X", "Y", "xG", "home_goals", "away_goals"])


def understat_team_season_shots(team_url):
    """Todos los tiros de los partidos de un equipo en una temporada (``https://understat.com/team/Arsenal/2024``)."""
    df = _shooting(team_url)
    if len(df) == 0:
        return df
    return _to_num(df.rename(columns=_SHOT_RENAMES), ["minute", "X", "Y", "xG", "home_goals", "away_goals"])


def understat_match_shots(match_url):
    """Tiros de un partido (``https://understat.com/match/12345``)."""
    df = _clean_json(match_url, "shotsData")
    if len(df) == 0:
        return df
    return _to_num(df.rename(columns=_SHOT_RENAMES), ["minute", "X", "Y", "xG", "home_goals", "away_goals"])


def understat_player_shots(player_url):
    """Todos los tiros de un jugador (``https://understat.com/player/1234``)."""
    return understat_match_shots(player_url)


def understat_match_players(match_url):
    """Estadísticas por jugador de un partido (minutos, xG, xA, xGChain, xGBuildup...)."""
    match_id = int(re.sub(r"[^0-9]", "", match_url))
    data, _ = _get_var(match_url, "rostersData")
    if not data:
        return pd.DataFrame()
    recs = []
    for side in ("h", "a"):
        block = data.get(side, {})
        recs.extend(block.values() if isinstance(block, dict) else block)
    r = pd.DataFrame(recs)

    def col(name, kind="int"):
        s = r[name] if name in r.columns else pd.Series([np.nan] * len(r))
        s = pd.to_numeric(s, errors="coerce") if kind != "str" else s.astype(object)
        return s.astype("Int64") if kind == "int" else s

    return pd.DataFrame({
        "match_id": match_id,
        "id": col("id"),
        "team_id": col("team_id"),
        "home_away": col("h_a", "str"),
        "player_id": col("player_id"),
        "swap_id": col("id"),
        "player": col("player", "str"),
        "position": col("position", "str"),
        "positionOrder": col("positionOrder"),
        "time_played": col("time"),
        "goals": col("goals"),
        "own_goals": col("own_goals"),
        "shots": col("shots"),
        "xG": col("xG", "num"),
        "yellow_card": col("yellow_card"),
        "red_card": col("red_card"),
        "roster_in": col("roster_in"),
        "roster_out": col("roster_out"),
        "key_passes": col("key_passes"),
        "assists": col("assists"),
        "xA": col("xA", "num"),
        "xGChain": col("xGChain", "num"),
        "xGBuildup": col("xGBuildup", "num"),
    })


def understat_match_stats(match_url):
    """Resumen del partido: probabilidades, goles, xG, tiros, deep, PPDA y xPTS de cada equipo."""
    html = _get_page(match_url)
    if not html:
        return pd.DataFrame()
    page = _http.parse_html(html)
    vals = [(n.text_content() or "").strip() for blk in
            page.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' scheme-block ') and "
                       "contains(concat(' ', normalize-space(@class), ' '), ' is-hide ') and @data-scheme='stats']")
            for n in blk.cssselect(".progress-value")]
    away = vals[0::2]
    home = vals[1::2]

    def g(lst, i):
        return lst[i] if len(lst) > i else np.nan

    def pct(v):
        return float(re.sub(r"[^0-9]", "", v)) / 100 if isinstance(v, str) and re.search(r"\d", v) else np.nan

    def num(v, integer=False):
        x = pd.to_numeric(v, errors="coerce")
        return int(x) if integer and not pd.isna(x) else x

    return pd.DataFrame([{
        "match_id": int(re.sub(r"[^0-9]", "", match_url)),
        "home_team": g(away, 0),
        "home_chances": pct(g(away, 1)),
        "home_goals": num(g(home, 2), True),
        "home_xG": num(g(home, 3)),
        "home_shots": num(g(home, 4), True),
        "home_shot_on_target": num(g(home, 5), True),
        "home_deep": num(g(home, 6), True),
        "home_PPDA": num(g(home, 7)),
        "home_xPTS": num(g(home, 8)),
        "draw_chances": pct(g(home, 1)),
        "away_team": g(home, 0),
        "away_chances": pct(g(away, 2)),
        "away_goals": num(g(away, 3), True),
        "away_xG": num(g(away, 4)),
        "away_shots": num(g(away, 5), True),
        "away_shot_on_target": num(g(away, 6), True),
        "away_deep": num(g(away, 7), True),
        "away_PPDA": num(g(away, 8)),
        "away_xPTS": num(g(away, 9)),
    }])


def understat_team_players_stats(team_url):
    """Estadísticas de temporada de los jugadores de uno o varios equipos."""
    frames = []
    for url in as_list(team_url):
        try:
            df = _clean_json(url, "playersData")
        except Exception as e:
            print(f"Error en {url}: {e}")
            continue
        if len(df) == 0:
            continue
        df = df.rename(columns={"team_title": "team_name", "id": "player_id"})
        for c in df.columns:
            conv = pd.to_numeric(df[c], errors="coerce")
            if df[c].notna().any() and conv[df[c].notna()].notna().all():
                df[c] = conv
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def understat_team_stats_breakdown(team_urls):
    """Desglose de estadísticas del equipo (situación, formación, estado del marcador, minuto, tipo de tiro...)."""
    frames = []
    for url in as_list(team_urls):
        try:
            html = _get_page(url)
            if not html:
                continue
            page = _http.parse_html(html)
            crumbs = [li.text_content() for b in page.cssselect(".breadcrumb") for li in b.cssselect("li")]
            team_name = crumbs[2] if len(crumbs) > 2 else np.nan
            opts = page.xpath('//*[@name="season"]//option[@selected]')
            season = pd.to_numeric(opts[0].get("value"), errors="coerce") if opts else np.nan
            data, _ = _get_var(url, "statisticsData", html=html)
            if not data:
                continue
            for group, stats in data.items():
                for stat_name, vals in stats.items():
                    row = {"team_name": team_name, "season_start_year": season, "stat_group_name": group,
                           "stat_name": stat_name}
                    flat = pd.json_normalize(vals, sep=".").iloc[0].to_dict() if isinstance(vals, dict) else {}
                    flat.pop("stat", None)
                    row.update(flat)
                    frames.append(row)
        except Exception as e:
            print(f"Error en {url}: {e}")
    return pd.DataFrame(frames)


def understat_available_teams(leagues):
    """Equipos disponibles en las ligas indicadas (lista si es una liga; dict si son varias)."""
    examples = {
        "EPL": "https://understat.com/team/Arsenal",
        "La liga": "https://understat.com/team/Barcelona",
        "Bundesliga": "https://understat.com/team/Bayern_Munich",
        "Serie A": "https://understat.com/team/AC_Milan",
        "Ligue 1": "https://understat.com/team/Paris_Saint_Germain",
        "RFPL": "https://understat.com/team/Spartak_Moscow",
    }
    out = {}
    for lg in as_list(leagues):
        if lg not in examples:
            print(f"League {lg} not found. Please check understats.com for the correct league name")
            continue
        html = _get_page(examples[lg])
        if not html:
            out[lg] = []
            continue
        page = _http.parse_html(html)
        txt = "".join(h.text_content() for h in page.cssselect(".header-wrapper"))
        txt = re.sub(r"([\n\t])|(\d{4}/\d{4})", "", txt)
        txt = re.sub(r"(?<!\s)([A-Z])", r"(&&)\1", txt)
        out[lg] = [t for t in txt.split("(&&)")[1:]]
    if len(as_list(leagues)) == 1:
        return next(iter(out.values()), [])
    return out


def understat_team_meta(team_names):
    """Metadatos de equipos: temporadas disponibles y URL de cada una."""
    frames = []
    for name in as_list(team_names):
        try:
            slug = name.replace(" ", "_")
            team_url = f"{UNDERSTAT}/team/{slug}"
            page = _http.load_page(team_url, cookies=_COOKIES)
            opts = page.xpath('//*[@name="season"]//option')
            df = pd.DataFrame({
                "team_name": slug,
                "year": pd.to_numeric([o.get("value") for o in opts], errors="coerce"),
                "season": [squish(o.text_content()) for o in opts],
            })
            df["url"] = team_url + "/" + df["year"].astype("Int64").astype(str)
            frames.append(df)
        except Exception as e:
            print(f"Error en {name}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_understat_league_shots(league):
    """Tiros precargados de todas las temporadas de una liga (sin visitar Understat)."""
    lg = _check_league(league)
    url = f"{DATA_REPO_RELEASES}/understat_shots/{janitor_clean_name(lg)}_shot_data.rds"
    df = _http.file_reader(url)
    if len(df) == 0:
        print("→ Data not loaded. Please check parameters.")
    else:
        ts = df.attrs.get("scrape_timestamp")
        if ts is not None:
            print(f"→ Data last updated {ts} UTC")
    return df


__all__ = [
    "understat_available_teams", "understat_league_match_results", "understat_league_season_shots",
    "understat_match_players", "understat_match_shots", "understat_match_stats", "understat_player_shots",
    "understat_team_meta", "understat_team_players_stats", "understat_team_season_shots",
    "understat_team_stats_breakdown", "load_understat_league_shots",
]
