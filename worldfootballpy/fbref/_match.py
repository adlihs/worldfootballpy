"""Funciones de FBref a nivel de partido.

Traducción de get_match_results.R, get_match_urls.R, get_match_report.R,
get_match_summary.R, get_match_lineups.R, get_match_shooting.R y
get_advanced_match_stats.R.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import _http
from .._table import first_row_as_char, html_table
from .._utils import (
    FBREF,
    all_competitions,
    as_list,
    as_numeric,
    clean_match_advanced_stats_data,
    is_na,
    progress,
    squish,
    texts,
    to_date,
)


# ----------------------------------------------------------------------------
# selección de URLs de temporadas
# ----------------------------------------------------------------------------

def _fixtures_urls(country, gender, season_end_year, tier, non_dom_league_url):
    seasons = all_competitions()
    gender = as_list(gender)
    years = as_list(season_end_year)
    if is_na(non_dom_league_url):
        df = seasons[seasons["competition_type"].astype(str).str.contains("Leagues", na=False)]
        df = df[
            df["country"].isin(as_list(country))
            & df["gender"].isin(gender)
            & df["season_end_year"].isin(years)
            & df["tier"].isin(as_list(tier))
            & df["fixtures_url"].notna()
        ]
    else:
        df = seasons[
            seasons["comp_url"].isin(as_list(non_dom_league_url))
            & seasons["gender"].isin(gender)
            & seasons["season_end_year"].isin(years)
            & seasons["fixtures_url"].notna()
        ]
    return list(dict.fromkeys(df.sort_values("season_end_year", kind="stable")["fixtures_url"]))


# ----------------------------------------------------------------------------
# resultados
# ----------------------------------------------------------------------------

def _get_each_season_results(fixture_url, time_pause=3):
    _http.sleep(time_pause)
    page = _http.load_page(fixture_url)

    tables = page.cssselect(".stats_table")
    table = tables[0]
    tbodies = table.cssselect("tbody")
    rows = tbodies[0].xpath("./tr") if tbodies else []

    def attrs_str(tr):
        return " ".join(f"{k} {v}" for k, v in tr.attrib.items())

    spacer_idx = [not re.search(r"spacer partial", attrs_str(tr)) for tr in rows]
    rows_kept = [tr for tr, keep in zip(rows, spacer_idx) if keep]
    idx_rm = [i for i, tr in enumerate(rows_kept) if "thead" in attrs_str(tr)]
    rows_final = [tr for i, tr in enumerate(rows_kept) if i not in idx_rm]

    summary = html_table(table)
    summary = summary.iloc[: len(spacer_idx)]
    summary = summary[np.array(spacer_idx[: len(summary)], dtype=bool)].reset_index(drop=True)
    if idx_rm:
        summary = summary.drop(index=[i for i in idx_rm if i < len(summary)]).reset_index(drop=True)

    def get_url(tr):
        a = tr.xpath('.//*[@data-stat="match_report"]//a')
        href = a[0].get("href") if a else None
        return FBREF + href if href else np.nan

    match_urls = [get_url(tr) for tr in rows_final]

    if "Time" in summary.columns:
        t = summary["Time"]
        summary = summary[t.isna() | (t.astype(str) != "Time")]
        match_urls = [u for u, keep in zip(match_urls, (t.isna() | (t.astype(str) != "Time")).tolist()) if keep]
    summary = summary.reset_index(drop=True)

    score = summary["Score"].astype(object).map(
        lambda s: squish(str(s).replace("–", " ")) if isinstance(s, str) else ""
    )
    parts = score.str.split(" ", n=1, expand=True) if len(score) else pd.DataFrame(columns=[0, 1])
    if parts.shape[1] < 2:
        parts[1] = np.nan
    home_goals = as_numeric(parts[0])
    away_goals = as_numeric(parts[1].map(lambda v: v.split(" ")[0] if isinstance(v, str) else v))
    summary = summary.drop(columns=["Score"])
    summary["HomeGoals"] = home_goals
    summary["AwayGoals"] = away_goals
    if "Attendance" in summary.columns:
        summary["Attendance"] = as_numeric(summary["Attendance"].astype(str).str.replace(",", "", regex=False))
    else:
        summary["Attendance"] = np.nan

    hg, ag = summary["HomeGoals"].copy(), summary["AwayGoals"].copy()
    summary["HomeGoals"] = np.where(hg.isna() & ag.notna(), ag, hg)
    summary["AwayGoals"] = np.where(ag.isna() & hg.notna(), hg, ag)

    summary.insert(0, "fixture_url", fixture_url)
    for c in ("Round", "Wk", "Day", "Date", "Time", "Home", "Away", "Venue", "Referee", "Notes"):
        if c not in summary.columns:
            summary[c] = np.nan

    if "xG" in summary.columns:
        out = summary[["fixture_url", "Round", "Wk", "Day", "Date", "Time", "Home", "HomeGoals"]].copy()
        out["Home_xG"] = as_numeric(summary["xG"])
        out["Away"] = summary["Away"]
        out["AwayGoals"] = summary["AwayGoals"]
        out["Away_xG"] = as_numeric(summary["xG.1"]) if "xG.1" in summary.columns else np.nan
        for c in ("Attendance", "Venue", "Referee", "Notes"):
            out[c] = summary[c]
    else:
        out = summary[["fixture_url", "Round", "Wk", "Day", "Date", "Time", "Home", "HomeGoals",
                       "Away", "AwayGoals", "Attendance", "Venue", "Referee", "Notes"]].copy()

    out["Wk"] = out["Wk"].map(lambda v: np.nan if is_na(v) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
    out["MatchURL"] = (match_urls + [np.nan] * len(out))[: len(out)]
    return out


def fb_match_results(country, gender, season_end_year, tier="1st", non_dom_league_url=np.nan, time_pause=3):
    """Resultados de los partidos de una liga/temporada(s) de FBref.

    Parameters
    ----------
    country : str o lista
        Código de tres letras del país (p. ej. ``"ENG"``, ``"CRC"``).
    gender : str o lista
        ``"M"`` o ``"F"``.
    season_end_year : int o lista
        Año(s) en que termina la temporada.
    tier : str
        Nivel de la liga: ``"1st"``, ``"2nd"``...
    non_dom_league_url : str, opcional
        URL de una competición no doméstica (copas, torneos internacionales).
    """
    fixtures = _fixtures_urls(country, gender, season_end_year, tier, non_dom_league_url)
    if not fixtures:
        raise ValueError("Data not available for the season(s) selected")

    frames = [_get_each_season_results(u, time_pause) for u in progress(fixtures, "fb_match_results")]
    results = pd.concat(frames, ignore_index=True)

    seasons = all_competitions()[
        ["competition_name", "gender", "country", "season_end_year", "seasons_urls", "fixtures_url"]
    ].rename(columns={"competition_name": "Competition_Name", "gender": "Gender",
                      "country": "Country", "season_end_year": "Season_End_Year"})
    seasons = seasons.drop_duplicates(subset=["fixtures_url"])
    merged = results.merge(seasons, left_on="fixture_url", right_on="fixtures_url", how="left")
    merged = merged.drop(columns=["seasons_urls", "fixtures_url", "fixture_url"])
    front = ["Competition_Name", "Gender", "Country", "Season_End_Year"]
    merged = merged[front + [c for c in merged.columns if c not in front]]
    merged["Date"] = to_date(merged["Date"])
    merged = merged.sort_values(
        ["Country", "Competition_Name", "Gender", "Season_End_Year", "Wk", "Date", "Time"],
        kind="stable", na_position="last",
    ).drop_duplicates().reset_index(drop=True)
    return merged


def fb_match_urls(country, gender, season_end_year, tier="1st", non_dom_league_url=np.nan, time_pause=3):
    """URLs de los informes de partido (match reports) de una liga/temporada(s)."""
    fixtures = _fixtures_urls(country, gender, season_end_year, tier, non_dom_league_url)
    urls = []
    for fx in progress(fixtures, "fb_match_urls"):
        _http.sleep(time_pause)
        page = _http.load_page(fx)
        hrefs = [a.get("href") for a in page.cssselect("td.left ~ .left + .left a")]
        urls.extend(dict.fromkeys(FBREF + h for h in hrefs if h))
    return [u for u in urls if "-History" not in u]


# ----------------------------------------------------------------------------
# match report
# ----------------------------------------------------------------------------

def _nth_text(nodes, i):
    t = texts(nodes)
    return t[i] if len(t) > i else np.nan


def _get_match_report_page(page) -> pd.DataFrame:
    langs = page.cssselect(".langs")
    game_url = np.nan
    if langs:
        en = langs[0].cssselect(".en")
        if en:
            game_url = en[0].get("href")

    def safe(fn, default=np.nan):
        try:
            v = fn()
            return default if v is None else v
        except Exception:
            return default

    league = safe(lambda: _nth_text(page.cssselect("h1 + div a:nth-child(1)"), 0))
    match_date = safe(lambda: page.cssselect(".venuetime")[0].get("data-venue-date"))
    matchweek = safe(lambda: _nth_text(page.cssselect("h1 + div"), 0))
    teams = page.cssselect("div + strong a")
    home_team = _nth_text(teams, 0)
    away_team = _nth_text(teams, 1)

    def formation(sel):
        ths = page.cssselect(sel + " th")
        if not ths:
            return np.nan
        t = (ths[0].text_content() or "").strip()
        return re.sub(r"\)", "", re.sub(r".*\(", "", t))

    scores = page.cssselect(".scores")
    score_vals = [s for sc in scores for s in sc.cssselect(".score")]
    xg_vals = [s for sc in scores for s in sc.cssselect(".score_xg")]

    def goals(sel):
        n = page.cssselect(sel)
        return squish(n[0].text_content()) if n else np.nan

    cards = page.cssselect(".cards")

    def count_cards(i, sel):
        if len(cards) <= i:
            return 0
        return len(cards[i].cssselect(sel))

    row = {
        "League": league,
        "Match_Date": match_date,
        "Matchweek": matchweek,
        "Home_Team": home_team,
        "Home_Formation": formation(".lineup#a"),
        "Home_Score": as_numeric(_nth_text(score_vals, 0)),
        "Home_xG": as_numeric(_nth_text(xg_vals, 0)),
        "Home_Goals": goals("#a"),
        "Home_Yellow_Cards": count_cards(0, "span.yellow_card, span.yellow_red_card"),
        "Home_Red_Cards": count_cards(0, "span.red_card, span.yellow_red_card"),
        "Away_Team": away_team,
        "Away_Formation": formation(".lineup#b"),
        "Away_Score": as_numeric(_nth_text(score_vals, 1)),
        "Away_xG": as_numeric(_nth_text(xg_vals, 1)),
        "Away_Goals": goals("#b"),
        "Away_Yellow_Cards": count_cards(1, "span.yellow_card, span.yellow_red_card"),
        "Away_Red_Cards": count_cards(1, "span.red_card, span.yellow_red_card"),
        "Game_URL": game_url,
    }
    return pd.DataFrame([row])


def _load_or_none(url):
    try:
        return _http.load_page(url)
    except Exception:
        return None


def fb_match_report(match_url, time_pause=3):
    """Información general del partido (equipos, marcador, xG, formaciones, tarjetas)."""
    frames = []
    for url in progress(as_list(match_url), "fb_match_report"):
        _http.sleep(time_pause)
        page = _load_or_none(url)
        if page is None:
            print(f"{url} is not available")
            continue
        frames.append(_get_match_report_page(page))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# match summary (eventos)
# ----------------------------------------------------------------------------

def _half(minute_str, is_pens=False):
    if is_pens:
        return 5
    try:
        m = float(re.sub(r"\+.*", "", str(minute_str)))
    except ValueError:
        return 5
    if m <= 45:
        return 1
    if 46 <= m <= 90:
        return 2
    if 91 <= m <= 105:
        return 3
    if 106 <= m <= 120:
        return 4
    return 5


def _parse_events(events_df: pd.DataFrame) -> pd.DataFrame:
    df = events_df.copy()
    es = df["events_string"].astype(str)
    df["Event_Time"] = es.str.replace(r"(&rsquor|\u2019).*", "", regex=True).str.strip()
    df["Is_Pens"] = df["Event_Time"].str.contains(r"[A-Z]", regex=True)
    df["Event_Half"] = [_half(t, p) for t, p in zip(df["Event_Time"], df["Is_Pens"])]

    def ev_time(t, pens):
        if pens:
            return 121.0
        if "+" in t:
            try:
                return float(re.sub(r"\+.*", "", t)) + float(re.sub(r".*\+", "", t))
            except ValueError:
                return np.nan
        return as_numeric(t)

    df["Event_Time"] = [ev_time(t, p) for t, p in zip(df["Event_Time"], df["Is_Pens"])]

    def ev_type(s):
        low = s.lower()
        if "penalty" in low:
            return "Penalty"
        if "own goal" in low:
            return "Own Goal"
        t = re.sub(r".* [^\x20-\x7E] ", "", s)
        return squish(re.sub(r"[0-9]:[0-9]", "", t))

    df["Event_Type"] = [ev_type(s) for s in es]
    players = es.str.replace(r".*;", "", regex=True).str.replace(r" [^\x20-\x7E] .*", "", regex=True)
    df["Score_Progression"] = players.str.extract(r"([0-9]:[0-9])", expand=False)
    players = players.str.replace(r"[0-9]:[0-9]", "", regex=True).map(squish)
    df["Penalty_Number"] = [
        as_numeric(re.sub(r"([0-9]+).*$", r"\1", p)) if pens else np.nan
        for p, pens in zip(players, df["Is_Pens"])
    ]
    df["Event_Players"] = players.str.replace(r"[0-9]+\s", "", regex=True)
    df.loc[df["Is_Pens"], "Event_Type"] = "Penalty Shootout"
    df = df.drop(columns=["events_string"])
    cols = ["Team", "Home_Away", "Event_Time", "Is_Pens", "Event_Half", "Event_Type",
            "Event_Players", "Score_Progression", "Penalty_Number"]
    df = df[cols]
    return df.sort_values(["Event_Half", "Event_Time"], kind="stable").reset_index(drop=True)


def fb_match_summary(match_url, time_pause=3):
    """Eventos del partido (goles, tarjetas, cambios, penales) a partir del match report."""
    frames = []
    for url in progress(as_list(match_url), "fb_match_summary"):
        _http.sleep(time_pause)
        page = _load_or_none(url)
        if page is None:
            print(f"Match Summary not available for {url}")
            continue
        report = _get_match_report_page(page)
        teams = page.cssselect("div + strong a")
        home_team, away_team = _nth_text(teams, 0), _nth_text(teams, 1)
        wrap = page.cssselect("#events_wrap")
        home_ev = [squish(e.text_content()) for w in wrap for e in w.cssselect(".a")]
        away_ev = [squish(e.text_content()) for w in wrap for e in w.cssselect(".b")]
        ev = pd.concat([
            pd.DataFrame({"Team": home_team, "Home_Away": "Home", "events_string": home_ev}),
            pd.DataFrame({"Team": away_team, "Home_Away": "Away", "events_string": away_ev}),
        ], ignore_index=True)
        if len(ev) == 0:
            continue
        ev = _parse_events(ev)
        rep = pd.concat([report] * len(ev), ignore_index=True)
        frames.append(pd.concat([rep, ev], axis=1))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# lineups
# ----------------------------------------------------------------------------

def _summary_tables(page):
    containers = page.cssselect(".table_container")
    out = []
    for c in containers:
        if re.search(r"summary$", c.get("id") or ""):
            out.extend(c.cssselect("table"))
    return out


def _formation_from_header(name):
    is_diamond = bool(re.search(r"\..$", name)) or "◆" in name
    if re.search("u", name, flags=re.I):
        name = re.sub(r"u\..*", "", name, flags=re.I)
    digits = re.findall(r"[0-9]", name)
    formation = "-".join(digits)
    if is_diamond:
        formation += "-diamond"
    return formation


def fb_match_lineups(match_url, time_pause=3):
    """Alineaciones (titulares y suplentes) de cada equipo, con minutos, goles y tarjetas."""
    frames = []
    for url in progress(as_list(match_url), "fb_match_lineups"):
        _http.sleep(time_pause)
        page = _load_or_none(url)
        if page is None:
            print(f"Lineups not available for {url}")
            continue
        try:
            frames.append(_match_lineup(page, url))
        except Exception:
            print(f"Lineups not available for {url}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _match_lineup(page, match_url):
    match_date = page.cssselect(".venuetime")[0].get("data-venue-date")
    lineups = [t for lu in page.cssselect(".lineup") for t in lu.cssselect("table")]
    teams = texts(page.cssselect("div + strong a"))
    stats_tables = _summary_tables(page)
    out = []
    for idx, home_or_away in ((0, "Home"), (1, "Away")):
        table = lineups[idx]
        raw = html_table(table, r_names=False)
        header = table.xpath(".//tr")[0].text_content().strip()
        formation = _formation_from_header(header)
        player_urls = [FBREF + (a.get("href") or "") for a in table.cssselect("a")]
        first = raw.iloc[:, 0].astype(str)
        bench = np.where(first == "Bench")[0]
        b = bench[0] if len(bench) else len(raw)
        pitch = raw.iloc[:b].copy()
        pitch["Starting"] = "Pitch"
        bench_df = raw.iloc[b + 1:].copy()
        bench_df["Starting"] = "Bench"
        lu = pd.concat([pitch, bench_df], ignore_index=True)
        lu = lu.iloc[:, [0, 1, -1]]
        lu.columns = ["Player_Num", "Player_Name", "Starting"]
        team = teams[idx] if len(teams) > idx else np.nan
        lu["Matchday"] = match_date
        lu["Team"] = team
        lu["Formation"] = formation
        lu["PlayerURL"] = (player_urls + [np.nan] * len(lu))[: len(lu)]
        lu["Player_Num"] = lu["Player_Num"].map(_num_to_str)

        info = clean_match_advanced_stats_data(html_table(stats_tables[idx]))
        info = info[info["Player_Num"].notna()].copy()
        info.insert(0, "Home_Away", home_or_away)
        info.insert(0, "Team", team)
        info["Player_Num"] = info["Player_Num"].map(_num_to_str)
        keep = ["Team", "Home_Away", "Player", "Player_Num"] + (["Nation"] if "Nation" in info.columns else []) + [
            "Pos", "Age", "Min", "Gls", "Ast", "CrdY", "CrdR"]
        info = info[[c for c in keep if c in info.columns]]

        lu = lu.merge(info, how="left", left_on=["Team", "Player_Name", "Player_Num"],
                      right_on=["Team", "Player", "Player_Num"]).drop(columns=["Player"])
        lu["Home_Away"] = lu["Home_Away"].fillna(home_or_away)
        front = ["Matchday", "Team", "Home_Away", "Formation", "Player_Num", "Player_Name", "Starting"]
        lu = lu[front + [c for c in lu.columns if c not in front]]
        lu["Matchday"] = to_date(lu["Matchday"])
        lu["MatchURL"] = match_url
        out.append(lu)
    return pd.concat(out, ignore_index=True)


def _num_to_str(v):
    if is_na(v):
        return np.nan
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ----------------------------------------------------------------------------
# shooting
# ----------------------------------------------------------------------------

def _prep_shot_df(shot_df: pd.DataFrame) -> pd.DataFrame:
    var_names = first_row_as_char(shot_df)
    names = [f"{a}_{b}" for a, b in zip(var_names, shot_df.columns)]
    names = [re.sub(r"_Var.[0-9]+", "", n) for n in names]
    names = [n.replace(".1.1", ".1").replace(".2.1", ".2").replace(".", "_") for n in names]
    df = shot_df.iloc[1:].copy()
    df.columns = names
    df["Match_Half"] = [_half(m) for m in df["Minute"].astype(str)]
    df = df[df["Minute"].astype(str) != ""]
    df = df[df["Minute"].notna()]
    return df.reset_index(drop=True)


def _add_player_href(df, parent, xpath):
    hrefs = [a.get("href") for a in parent.xpath(xpath)]
    hrefs = (hrefs + [np.nan] * len(df))[: len(df)]
    df = df.copy()
    pos = list(df.columns).index("Player") + 1 if "Player" in df.columns else len(df.columns)
    df.insert(pos, "Player_Href", hrefs)
    return df


def fb_match_shooting(match_url, time_pause=3):
    """Detalle de cada tiro del partido (minuto, jugador, resultado, distancia, SCA)."""
    frames = []
    for url in progress(as_list(match_url), "fb_match_shooting"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        venue = page.cssselect(".venuetime")
        match_date = venue[0].get("data-venue-date") if venue else np.nan
        switcher = page.cssselect("#switcher_shots")
        divs = [d for s in switcher for d in s.cssselect("div")]
        if not divs:
            print(f"Detailed shot data unavailable for {url}")
            continue
        match_frames = []
        for i, ha in ((1, "Home"), (2, "Away")):
            if len(divs) <= i:
                continue
            tables = divs[i].cssselect("table")
            if not tables:
                continue
            raw = html_table(tables[0])
            if len(raw) == 0:
                continue
            df = _prep_shot_df(raw)
            df.insert(0, "Date", match_date)
            df["Home_Away"] = ha
            if "Player" in df.columns:
                df = _add_player_href(df, divs[i], ".//tbody/tr/td[@data-stat='player']/a")
            match_frames.append(df)
        if match_frames:
            df = pd.concat(match_frames, ignore_index=True)
            front = [c for c in ["Date", "Squad", "Home_Away", "Match_Half"] if c in df.columns]
            frames.append(df[front + [c for c in df.columns if c not in front]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# estadísticas avanzadas por partido
# ----------------------------------------------------------------------------

_STAT_PATTERNS = {
    "summary": r"summary$",
    "passing": r"passing$",
    "passing_types": r"passing_types",
    "defense": r"defense$",
    "possession": r"possession$",
    "misc": r"misc$",
    "keeper": r"keeper_stats",
}


def fb_advanced_match_stats(match_url, stat_type, team_or_player, time_pause=3):
    """Estadísticas avanzadas de un partido, por jugador o por equipo.

    ``stat_type``: ``"summary"``, ``"passing"``, ``"passing_types"``, ``"defense"``,
    ``"possession"``, ``"misc"``, ``"keeper"``.
    ``team_or_player``: ``"team"`` o ``"player"``.
    """
    if stat_type not in _STAT_PATTERNS:
        raise ValueError(f"stat_type debe ser uno de {list(_STAT_PATTERNS)}")
    frames = []
    for url in progress(as_list(match_url), "fb_advanced_match_stats"):
        _http.sleep(time_pause)
        page = _load_or_none(url)
        if page is None:
            print(f"Stats data not available for {url}")
            continue
        report = _get_match_report_page(page)
        teams = texts(page.cssselect("div + strong a"))
        tables = []
        for c in page.cssselect(".table_container"):
            if re.search(_STAT_PATTERNS[stat_type], c.get("id") or ""):
                tables.extend(c.cssselect("table"))
        if not tables:
            print(f"NOTE: Stat Type '{stat_type}' is not found for this match. Check {url} to see if it exists.")
            continue
        parts = []
        for idx, ha in ((0, "Home"), (1, "Away")):
            if len(tables) <= idx:
                continue
            st = clean_match_advanced_stats_data(html_table(tables[idx]))
            st = _add_player_href(st, tables[idx], ".//tbody/tr/th/a")
            st.insert(0, "Home_Away", ha)
            st.insert(0, "Team", teams[idx] if len(teams) > idx else np.nan)
            parts.append(st)
        out = pd.concat(parts, ignore_index=True)
        if stat_type != "keeper" and "Player" in out.columns:
            is_team = out["Player"].astype(str).str.contains(" Players", regex=False)
            if team_or_player == "team":
                drop = [c for c in ["Player", "Player_Num", "Nation", "Pos", "Age"] if c in out.columns]
                out = out[is_team].drop(columns=drop)
            else:
                out = out[~is_team]
        out = out.reset_index(drop=True)
        if len(out) == 0:
            print(f"NOTE: Stat Type '{stat_type}' is not found for this match. Check {url} to see if it exists.")
            continue
        rep = pd.concat([report] * len(out), ignore_index=True)
        frames.append(pd.concat([rep, out], axis=1))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
