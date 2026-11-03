"""Funciones de FBref a nivel de equipo.

Traducción de fb_team_goal_logs.R, fb_team_match_log_stats.R,
fb_team_match_stats.R, fb_team_player_stats.R, fbref_wages.R y
team_match_results.R.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import _http
from .._table import first_row_as_char, html_table
from .._utils import (
    FBREF,
    as_list,
    as_numeric,
    clean_numeric,
    clean_table_names,
    progress,
    squish,
    texts,
)
from ._match import _load_or_none, _nth_text
from ._players import _GOAL_RENAMES, _goal_log_url, _goal_table


def _team_name_from_url(url):
    return re.sub(r".*/", "", url).replace("-Stats", "").replace("-", " ")


def fb_team_goal_logs(team_urls, time_pause=3, for_or_against="for"):
    """Registro de goles a favor y/o en contra de equipos.

    ``for_or_against``: ``"for"``, ``"against"`` o ``"both"``.
    """
    frames = []
    for url in progress(as_list(team_urls), "fb_team_goal_logs"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        log_url = _goal_log_url(page)
        if not log_url:
            continue
        try:
            log_page = _http.load_page(log_url)
        except Exception:
            continue
        parts = []
        if for_or_against in ("for", "both"):
            parts.append(_goal_table(log_page, 0, "For_or_Against", "for"))
        if for_or_against in ("against", "both"):
            parts.append(_goal_table(log_page, 1, "For_or_Against", "against"))
        parts = [p for p in parts if len(p)]
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True).rename(columns=_GOAL_RENAMES)
        df = df[df["Rk"].notna()]
        df = df.sort_values(["For_or_Against", "Date", "Minute"], ascending=[False, True, True], kind="stable")
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


_LOG_TYPES = ["shooting", "keeper", "passing", "passing_types", "gca", "defense", "possession", "misc"]


def fb_team_match_log_stats(team_urls, stat_type, time_pause=3):
    """Estadísticas partido a partido (a favor y en contra) de equipos.

    ``stat_type``: ``"shooting"``, ``"keeper"``, ``"passing"``, ``"passing_types"``, ``"gca"``,
    ``"defense"``, ``"possession"``, ``"misc"``.
    """
    if stat_type not in _LOG_TYPES:
        raise ValueError("check stat type")
    frames = []
    for url in progress(as_list(team_urls), "fb_team_match_log_stats"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        team_name = _team_name_from_url(url)
        filters = [f for f in page.cssselect("#content .filter") if "Match Log Types" in f.text_content()]
        hrefs = [a.get("href") for f in filters for a in f.cssselect("a") if a.get("href")]
        selected = [h for h in hrefs if (stat_type + "/") in h]
        if not selected:
            print(f"{stat_type} stat not available for {team_name}")
            continue
        _http.sleep(time_pause)
        stat_page = _http.load_page(FBREF + selected[0])
        containers = stat_page.cssselect("#all_matchlogs #switcher_matchlogs .table_container")

        opponent_names = []
        parts = []
        for i, label in ((0, "For"), (1, "Against")):
            if len(containers) <= i:
                continue
            tables = containers[i].cssselect("table")
            if not tables:
                continue
            df = html_table(tables[0])
            if len(df) == 0:
                continue
            prefix = "For." if i == 0 else "Against."
            df.columns = ["" if prefix in c else c for c in df.columns]
            df.columns = [f"Var.{k + 1}" if c == "" else c for k, c in enumerate(df.columns)]
            df = clean_table_names(df)
            df = df[df["Date"].astype(str) != ""]
            df = df[df["Date"].notna()].copy()
            df["ForAgainst"] = label
            if i == 0:
                head_rows = containers[0].cssselect("thead tr")
                tab_names = texts(head_rows[1].cssselect("th")) if len(head_rows) > 1 else []
                opp_idx = [k + 1 for k, t in enumerate(tab_names) if "opponent" in t.lower()]
                if opp_idx:
                    opponent_names = texts(containers[0].cssselect(f".left:nth-child({opp_idx[0]}) a"))
            df["Opponent"] = (opponent_names + [np.nan] * len(df))[: len(df)]
            parts.append(df)
        if not parts:
            continue
        log = pd.concat(parts, ignore_index=True)
        log.insert(0, "Team", team_name)
        log.insert(0, "Team_Url", url)
        front = ["Team_Url", "Team", "ForAgainst"]
        log = log[front + [c for c in log.columns if c not in front and c != "Match Report"]]
        keep = {"Team_Url", "Team", "ForAgainst", "Date", "Time", "Comp", "Round", "Day", "Venue",
                "Result", "GF", "GA", "Opponent"}
        for c in log.columns:
            if c not in keep:
                log[c] = clean_numeric(log[c])
        frames.append(log)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


_EXTRA = ["Fouls", "Corners", "Crosses", "Touches", "Tackles", "Interceptions", "Aerials Won",
          "Clearances", "Offsides", "Goal Kicks", "Throw Ins", "Long Balls"]


def _get_team_match_stats(page) -> pd.DataFrame:
    langs = page.cssselect(".langs")
    game_url = np.nan
    if langs and langs[0].cssselect(".en"):
        game_url = langs[0].cssselect(".en")[0].get("href")
    team_stats = [tr.text_content() for ts in page.cssselect("#team_stats") for tr in ts.cssselect("tr")]
    extra = "".join(n.text_content() for n in page.cssselect("#team_stats_extra"))
    if not team_stats and not extra:
        print(f"Team stats data is missing for {game_url}. Returning an empty dataframe.")
        return pd.DataFrame()

    hp = ap = np.nan
    hsp = hpass = hacc = asp = apass = aacc = np.nan
    for i, row in enumerate(team_stats):
        if "Possession" in row and i + 1 < len(team_stats):
            nxt = team_stats[i + 1]
            m1 = re.search(r"^\s*(\d+)%", nxt)
            m2 = re.search(r"(\d+)%\s*$", nxt)
            hp = float(m1.group(1)) if m1 else np.nan
            ap = float(m2.group(1)) if m2 else np.nan
            break
    for i, row in enumerate(team_stats):
        if "Passing Accuracy" in row and i + 1 < len(team_stats):
            nxt = team_stats[i + 1]
            m = re.search(r"(\d+)\s+of\s+(\d+).+?(\d+)%", nxt, flags=re.S)
            if m:
                hsp, hpass, hacc = (float(x) for x in m.groups())
            m = re.search(r"(\d+)%.+?(\d+)\s+of\s+(\d+)", nxt, flags=re.S)
            if m:
                aacc, asp, apass = (float(x) for x in m.groups())
            break

    teams = page.cssselect("div + strong a")
    cards = page.cssselect(".cards")

    def count(i, sel):
        return len(cards[i].cssselect(sel)) if len(cards) > i else 0

    def formation(sel):
        ths = page.cssselect(sel + " th")
        if not ths:
            return np.nan
        return re.sub(r"\)", "", re.sub(r".*\(", "", (ths[0].text_content() or "").strip()))

    def home_extra(lbl):
        m = re.search(r"\d{1,4}(?=" + lbl + ")", extra)
        return float(m.group(0)) if m else np.nan

    def away_extra(lbl):
        m = re.search(r"(?<=" + lbl + r")\d{1,4}", extra)
        return float(m.group(0)) if m else np.nan

    league = texts(page.cssselect("h1 + div a:nth-child(1)"))
    venue = page.cssselect(".venuetime")
    row = {
        "League": league[0] if league else np.nan,
        "Match_Date": venue[0].get("data-venue-date") if venue else np.nan,
        "Matchweek": _nth_text(page.cssselect("h1 + div"), 0),
        "Home_Team": _nth_text(teams, 0),
        "Home_Formation": formation(".lineup#a"),
        "Home_Possession": hp, "Home_Success_Pass": hsp, "Home_Pass": hpass, "Home_Passing_Accuracy": hacc,
    }
    for lbl in _EXTRA:
        row["Home_" + lbl.replace(" ", "_")] = home_extra(lbl)
    row.update({
        "Home_Yellow_Cards": count(0, "span.yellow_card, span.yellow_red_card"),
        "Home_Red_Cards": count(0, "span.red_card, span.yellow_red_card"),
        "Away_Team": _nth_text(teams, 1),
        "Away_Formation": formation(".lineup#b"),
        "Away_Possession": ap, "Away_Success_Pass": asp, "Away_Pass": apass, "Away_Passing_Accuracy": aacc,
    })
    for lbl in _EXTRA:
        row["Away_" + lbl.replace(" ", "_")] = away_extra(lbl)
    row.update({
        "Away_Yellow_Cards": count(1, "span.yellow_card, span.yellow_red_card"),
        "Away_Red_Cards": count(1, "span.red_card, span.yellow_red_card"),
        "Game_URL": game_url,
    })
    return pd.DataFrame([row])


def fb_team_match_stats(match_url, time_pause=3):
    """Estadísticas de equipo de un partido: posesión, precisión de pase, faltas, córners, etc."""
    frames = []
    for url in progress(as_list(match_url), "fb_team_match_stats"):
        _http.sleep(time_pause)
        page = _load_or_none(url)
        if page is None:
            print(f"{url} is not available")
            continue
        frames.append(_get_team_match_stats(page))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


_TEAM_PLAYER_STEPS = [
    (r"\..[0-9]", ""), (r"\.[0-9]", ""), (r"\.", "_"), (r"_Var", ""), (r"#", "Player_Num"),
    (r"%", "_percent"), (r"_Performance", ""), (r"_Penalty", ""), (r"1/3", "Final_Third"),
    (r"\+/-", "Plus_Minus"), (r"/", "_per_"), (r"-", "_minus_"), (r"90s", "Mins_Per_90"), (r"__", "_"),
]
_TEAM_PLAYER_TYPES = ["standard", "shooting", "passing", "passing_types", "gca", "defense", "possession",
                      "playing_time", "misc", "keeper", "keeper_adv"]


def fb_team_player_stats(team_urls, stat_type, time_pause=3):
    """Estadísticas de temporada de todos los jugadores de un equipo.

    ``stat_type``: ``"standard"``, ``"shooting"``, ``"passing"``, ``"passing_types"``, ``"gca"``,
    ``"defense"``, ``"possession"``, ``"playing_time"``, ``"misc"``, ``"keeper"``, ``"keeper_adv"``.
    """
    if stat_type not in _TEAM_PLAYER_TYPES:
        raise ValueError("check stat type")
    frames = []
    for url in progress(as_list(team_urls), "fb_team_player_stats"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        spans = [s for h in page.cssselect("h1") for s in h.cssselect("span")]
        team_season = spans[0].text_content() if spans else ""
        m = re.search(r"(\d+)-(\d+)", team_season)
        season = m.group(0) if m else np.nan
        squad = squish(re.sub(r"\sStats", "", re.sub(r"(\d+)-(\d+)", "", team_season)))
        league = spans[1].text_content().replace("(", "").replace(")", "") if len(spans) > 1 else np.nan
        tabs = page.cssselect(".table_container")
        wrappers = [w.get("id") for c in page.cssselect("#content") for w in c.cssselect(".table_wrapper")]
        idx = [i for i, n in enumerate(wrappers) if n and re.search(f"all_stats_{stat_type}$", n)]
        if not idx:
            raise ValueError(f"Stat: {stat_type} not available for {squad}")
        table = tabs[idx[0]].cssselect("table")[0]
        tab = html_table(table)
        names = [f"{a}_{b}" for a, b in zip(first_row_as_char(tab), tab.columns)]
        for p, r in _TEAM_PLAYER_STEPS:
            names = [re.sub(p, r, n) for n in names]
        tab = tab.iloc[1:].copy()
        tab.columns = names
        tab = tab.reset_index(drop=True)
        hit = np.where(tab["Player"].astype(str).str.contains("Squad ", regex=False))[0]
        if len(hit):
            tab = tab.iloc[: hit.min()].copy()
        tab = tab.drop(columns=[c for c in ["Matches"] if c in tab.columns])
        if "Nation" in tab.columns:
            tab["Nation"] = tab["Nation"].astype(object).map(lambda v: re.sub(r"^.*? ", "", v) if isinstance(v, str) else v)
        for c in tab.columns:
            if c not in ("Player", "Nation", "Pos", "Age"):
                tab[c] = clean_numeric(tab[c])
        player_urls = []
        for tr in table.cssselect("tbody tr"):
            a = tr.cssselect("th a")
            player_urls.append(FBREF + a[0].get("href") if a and a[0].get("href") else np.nan)
        tab["PlayerURL"] = (player_urls + [np.nan] * len(tab))[: len(tab)]
        tab.insert(0, "Comp", league)
        tab.insert(0, "Squad", squad)
        tab.insert(0, "Season", season)
        frames.append(tab)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _split_wage(val):
    """'£ 100,000 (€ 115,000, $125,000)' -> ['£ 100,000 ', '€ 115,000', '$125,000)']."""
    if not isinstance(val, str):
        return [np.nan, np.nan, np.nan]
    first, _, rest = val.partition("(")
    if not _:
        return [first, np.nan, np.nan]
    second, _, third = rest.partition(", ")
    return [first, second, third if _ else np.nan]


def _wage_currency(v):
    if not isinstance(v, str):
        return np.nan
    if "€" in v:
        return "EUR"
    if "£" in v:
        return "GBP"
    if "$" in v:
        return "USD"
    return np.nan


def fb_squad_wages(team_urls, time_pause=3):
    """Salarios estimados (semanales y anuales, en EUR/GBP/USD) de la plantilla."""
    frames = []
    for url in progress(as_list(team_urls), "fb_squad_wages"):
        _http.sleep(time_pause)
        pg = _http.load_page(url)
        team_name = _team_name_from_url(url)
        league = texts(pg.cssselect(".prevnext + p a"))
        league = league[0] if len(league) == 1 else (league if league else np.nan)
        h1 = pg.cssselect("h1")
        season = squish(h1[0].text_content()).split(" ")[0] if h1 else np.nan
        links = pg.cssselect("#inner_nav .hoversmooth a")
        hrefs = list(dict.fromkeys(a.get("href") for a in links if "Wages" in a.text_content()))
        if not hrefs:
            print(f"NOTE: Wage data is not available for {url}. Check {url} to see if it exists.")
            continue
        _http.sleep(time_pause)
        wage_pg = _load_or_none(FBREF + hrefs[0])
        if wage_pg is None:
            print(f"NOTE: Wage data is not available for {url}. Check {url} to see if it exists.")
            continue
        tables = wage_pg.cssselect(".stats_table")
        table = tables[0]
        purls = []
        for tr in table.cssselect("tbody tr"):
            a = tr.cssselect("th a")
            purls.append(FBREF + a[0].get("href") if a and a[0].get("href") else np.nan)
        raw = html_table(table)
        raw["Url"] = (purls + [np.nan] * len(raw))[: len(raw)]
        raw = raw[~raw["Player"].astype(str).str.contains("Players", regex=False)].copy()
        raw["Nation"] = raw["Nation"].astype(object).map(lambda v: re.sub(r"^.*? ", "", v) if isinstance(v, str) else v)
        if "Notes" not in raw.columns:
            raw["Notes"] = np.nan
        id_cols = ["Player", "Nation", "Pos", "Age", "Notes", "Url"]

        records = []
        for _, r in raw.iterrows():
            base = {c: r.get(c, np.nan) for c in id_cols}
            vals = {}
            for col, label in (("Weekly.Wages", "WeeklyWage"), ("Annual.Wages", "AnnualWage")):
                for piece in _split_wage(r.get(col, np.nan)):
                    if not isinstance(piece, str):
                        continue
                    v = piece.replace(" ", "").replace(",", "").replace(")", "")
                    cur = _wage_currency(v)
                    num = pd.to_numeric(re.sub(r"[^\x20-\x7E]", "", v).replace("$", ""), errors="coerce")
                    if isinstance(cur, str) and not pd.isna(num):
                        vals[label + cur] = num
            records.append({**base, **vals})
        wide = pd.DataFrame(records)
        wide.insert(0, "Season", season)
        wide.insert(0, "Comp", league if not isinstance(league, list) else ", ".join(league))
        wide.insert(0, "Team", team_name)
        wage_cols = [c for c in wide.columns if "Wage" in c]
        wide = wide[["Team", "Comp", "Season", "Player", "Nation", "Pos", "Age"] + wage_cols + ["Notes", "Url"]]
        frames.append(wide)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fb_team_match_results(team_url, time_pause=3):
    """Resultados de todos los partidos de la temporada de un equipo (todas las competiciones)."""
    frames = []
    for url in progress(as_list(team_url), "fb_team_match_results"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        team_name = _team_name_from_url(url)
        opponents = texts(page.cssselect(".left:nth-child(10) a"))
        tables = [t for a in page.cssselect("#all_matchlogs") for t in a.cssselect("table")]
        log = html_table(tables[0])
        log["Opponent"] = (opponents + [np.nan] * len(log))[: len(log)]
        log.insert(0, "Team", team_name)
        log.insert(0, "Team_Url", url)
        log = log.drop(columns=[c for c in ["Match.Report"] if c in log.columns])
        if "Attendance" in log.columns:
            log["Attendance"] = as_numeric(log["Attendance"].astype(str).str.replace(",", "", regex=False))
        for c in ("GF", "GA"):
            if c in log.columns:
                log[c] = log[c].map(lambda v: np.nan if pd.isna(v) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
        frames.append(log)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


__all__ = ["fb_team_goal_logs", "fb_team_match_log_stats", "fb_team_match_stats", "fb_team_player_stats",
           "fb_squad_wages", "fb_team_match_results"]
