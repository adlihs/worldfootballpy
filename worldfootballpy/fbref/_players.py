"""Funciones de FBref a nivel de jugador.

Traducción de fb_player_goal_logs.R, fb_player_info.R, fb_player_match_logs.R
y fb_player_scouting.R.
"""

from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

from .. import _http
from .._table import html_table
from .._utils import (
    FBREF,
    as_list,
    clean_numeric,
    clean_table_names,
    progress,
    squish,
    texts,
)


def _goal_log_url(page):
    links = page.cssselect("#inner_nav .hoversmooth a")
    names = texts(links)
    idx = [i for i, t in enumerate(names) if "Goal Logs" in t]
    if idx:
        i = idx[0]
    else:
        allc = [i for i, t in enumerate(names) if "All Competitions" in t]
        if len(allc) < 4:
            return None
        i = allc[3]
    href = links[i].get("href")
    return FBREF + href if href else None


def _goal_table(page, i, label_col, label):
    tables = page.cssselect(".stats_table")
    if len(tables) <= i:
        return pd.DataFrame()
    df = html_table(tables[i])
    for c in df.columns:
        if any(k in c for k in ("Minute", "Goalkeeper", "Assist", "Notes")):
            df[c] = df[c].map(lambda v: np.nan if v is None or (isinstance(v, float) and np.isnan(v))
                              else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
    df[label_col] = label
    return df


_GOAL_RENAMES = {"Body.Part": "Body_Part", "Type": "Type1", "Type.1": "Type2"}


def fb_player_goal_logs(player_urls, time_pause=3, goals_or_assists="goals"):
    """Registro de goles y/o asistencias de jugadores.

    ``goals_or_assists``: ``"goals"``, ``"assists"`` o ``"both"``.
    """
    frames = []
    for url in progress(as_list(player_urls), "fb_player_goal_logs"):
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
        if goals_or_assists in ("goals", "both"):
            parts.append(_goal_table(log_page, 0, "Goal_or_Assist", "goal"))
        if goals_or_assists in ("assists", "both"):
            parts.append(_goal_table(log_page, 1, "Goal_or_Assist", "assist"))
        parts = [p for p in parts if len(p)]
        if not parts:
            continue
        df = pd.concat(parts, ignore_index=True).rename(columns=_GOAL_RENAMES)
        df = df[df["Rk"].notna()]
        df = df.sort_values(["Goal_or_Assist", "Rk"], ascending=[False, True], kind="stable")
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _xpath_text(page, xpath):
    n = page.xpath(xpath)
    if not n:
        return np.nan
    t = squish(n[0].text_content())
    return t if t else np.nan


def fb_player_info(player_urls, time_pause=3):
    """Ficha del jugador: nombre, posición, pie, altura, peso, nacimiento, club, salario, redes."""
    rows = []
    for url in progress(as_list(player_urls), "fb_player_info"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        h1 = page.cssselect("h1")
        full_name = squish(h1[0].text_content()) if h1 else np.nan
        pos_txt = _xpath_text(page, "//p[contains(., 'Position:')]")
        position = footed = np.nan
        if isinstance(pos_txt, str):
            parts = pos_txt.split("▪", 1)
            position = parts[0].replace("Position:", "").strip() or np.nan
            if len(parts) > 1:
                footed = parts[1].replace("Footed:", "").strip() or np.nan
        hw = _xpath_text(page, "//p[contains(., 'cm')]")
        height = re.search(r"\d+cm", hw).group(0) if isinstance(hw, str) and re.search(r"\d+cm", hw) else np.nan
        weight = re.search(r"\d+kg", hw).group(0) if isinstance(hw, str) and re.search(r"\d+kg", hw) else np.nan
        birth = page.cssselect("#necro-birth")
        birth_date = birth[0].get("data-birth") if birth else np.nan
        age = np.nan
        if isinstance(birth_date, str) and birth_date:
            age = _age_string(birth_date)
        bp = _xpath_text(page, "//p[contains(., 'Born:')]//span[contains(., 'in ')]")
        birth_place = re.sub(r"^in ", "", bp).strip() if isinstance(bp, str) else np.nan
        wages_n = page.cssselect(".important.poptip")
        rows.append({
            "full_name": full_name or np.nan,
            "position": position,
            "footed": footed,
            "height": height,
            "weight": weight,
            "birth_date": birth_date if birth_date else np.nan,
            "age": age,
            "birth_place": birth_place,
            "national_team": _xpath_text(page, "//p[contains(., 'National Team:')]/a"),
            "club": _xpath_text(page, "//p[contains(., 'Club:')]/a"),
            "wages": squish(wages_n[0].text_content()) if wages_n else np.nan,
            "twitter": _xpath_text(page, "//p[contains(., 'Twitter:')]/a"),
            "instagram": _xpath_text(page, "//p[contains(., 'Instagram:')]/a"),
        })
    return pd.DataFrame(rows)


def _age_string(birth_date: str, today: date | None = None) -> str:
    today = today or date.today()
    b = date.fromisoformat(birth_date[:10])

    def bday(year):
        try:
            return date(year, b.month, b.day)
        except ValueError:  # 29 de febrero
            return date(year, 3, 1)

    years = today.year - b.year
    this_year = bday(today.year)
    if this_year > today:
        years -= 1
        last = bday(today.year - 1)
    else:
        last = this_year
    return f"{years}-{(today - last).days}d"


_LOG_NAMES = {
    "Summary": "summary", "Goalkeeping": "keepers", "Passing": "passing", "Pass Types": "passing_types",
    "Goal and Shot Creation": "gca", "Defensive Actions": "defense", "Possession": "possession",
    "Miscellaneous Stats": "misc",
}


def fb_player_match_logs(player_url, season_end_year, stat_type, time_pause=3):
    """Registro partido a partido de un jugador en una temporada.

    ``stat_type``: ``"summary"``, ``"keepers"``, ``"passing"``, ``"passing_types"``, ``"gca"``,
    ``"defense"``, ``"possession"``, ``"misc"``.
    """
    if stat_type not in _LOG_NAMES.values():
        raise ValueError("check stat type")
    _http.sleep(time_pause)
    page = _http.load_page(player_url)
    h1 = page.cssselect("h1")
    player_name = squish(h1[0].text_content()) if h1 else np.nan
    cats = [c for nav in page.cssselect("#inner_nav") for c in nav.cssselect(".full.hasmore")]
    cats = [c for c in cats if any("Match Logs" in t for t in texts(c.cssselect("span")))]
    logs = []
    for c in cats:
        ps = texts(c.cssselect("p"))
        uls = c.cssselect("ul")
        for name, ul in zip(ps, uls):
            name = name.replace("Match Logs (", "").replace(")", "")
            for a in ul.cssselect("li a"):
                logs.append({"log_name": name, "log_urls": a.get("href"), "season": (a.text_content() or "").strip()})
    logs = pd.DataFrame(logs, columns=["log_name", "log_urls", "season"])
    logs["season_end"] = logs["season"].str.replace(r".*-", "", regex=True)
    logs["stat"] = logs["log_name"].map(_LOG_NAMES)
    filt = logs[(logs["stat"] == stat_type) & (logs["season_end"] == str(season_end_year))]
    if len(filt) == 0:
        raise ValueError(f"check stat type: {stat_type} or season end: {season_end_year} exists")

    frames = []
    non_num = {"Player", "Season", "Date", "Day", "Comp", "Round", "Venue", "Result", "Squad",
               "Opponent", "Start", "Pos"}
    for _, row in filt.iterrows():
        _http.sleep(1)
        stat_page = _http.load_page(FBREF + row["log_urls"])
        table = [t for c in stat_page.cssselect(".table_container") for t in c.cssselect("table")][0]
        tab = clean_table_names(html_table(table))
        tab = tab[tab["Date"].astype(str) != ""]
        tab = tab[tab["Date"].notna()].copy()
        for col in ("Squad", "Opponent"):
            if col in tab.columns:
                tab[col] = tab[col].astype(str).str.replace(r"^.*?([A-Z])", r"\1", n=1, regex=True)
        tab.insert(0, "Season", row["season"])
        tab.insert(0, "Player", player_name)
        tab = tab.drop(columns=[c for c in tab.columns if c == "Match Report"])
        for col in tab.columns:
            if col not in non_num:
                tab[col] = clean_numeric(tab[col])
        frames.append(tab)
    return pd.concat(frames, ignore_index=True)


def fb_player_scouting_report(player_url, pos_versus, league_comp_name=None, time_pause=3):
    """Informe de scouting (percentiles vs. jugadores de su posición).

    ``pos_versus``: ``"primary"`` (posición principal) o ``"secondary"``.
    ``league_comp_name``: filtra por periodo/competición (p. ej. ``"Last 365 Days Men's Big 5 Leagues, UCL, UEL"``).
    """
    _http.sleep(time_pause)
    page = _http.load_page(player_url)
    h1 = page.cssselect("h1")
    player_name = squish(h1[0].text_content()) if h1 else np.nan
    cats = [c for nav in page.cssselect("#inner_nav") for c in nav.cssselect(".full.hasmore")]
    cats = [c for c in cats if any("Scouting Report" in t for t in texts(c.cssselect("span")))]
    lis = [li for c in cats for li in c.cssselect("ul li")]
    urls = [FBREF + (a.get("href") or "") for li in lis for a in li.cssselect("a")]
    names = [squish(li.text_content()) for li in lis]
    if league_comp_name is not None:
        pattern = "|".join(as_list(league_comp_name))
        keep = [i for i, n in enumerate(names) if re.search(pattern, n)]
        if not keep:
            raise ValueError(f"'{league_comp_name}' not a valid value for `league_comp_name`. "
                             "Please re-copy and paste the correct value(s)")
        urls = [urls[i] for i in keep]

    frames = []
    for n, url in enumerate(urls):
        _http.sleep(time_pause)
        pg = _http.load_page(url)
        filt = pg.cssselect(".filter")
        periods = []
        if filt:
            for d in filt[0].cssselect("div"):
                t = squish(d.text_content())
                if t not in periods:
                    periods.append(t)
        period = periods[n] if len(periods) > n else np.nan
        outer = [d for f in pg.cssselect(".filter.switcher") for d in f.cssselect("div")]
        if len(outer) == 1:
            idx = 0
            versus = squish(outer[0].text_content())
        elif len(outer) > 1:
            idx = 1 if pos_versus != "primary" else 0
            versus = squish(outer[idx].text_content())
        else:
            raise ValueError(f"Full scouting report not available for {player_name}")
        containers = [c for a in pg.cssselect("#all_scout_full") for c in a.cssselect(".table_container")]
        table = containers[idx].cssselect("table")[0]
        raw = html_table(table, header=False, convert=False)
        raw = raw[raw.iloc[:, 0].astype(str) != ""].reset_index(drop=True)
        raw = raw.iloc[:, :3]
        raw.columns = ["Statistic", "Per90", "Percentile"]

        # El nombre de grupo es la fila anterior a cada cabecera "Statistic";
        # el primer grupo es "Standard".
        group = "Standard"
        rows = []
        records = raw.to_dict("records")
        for i, r in enumerate(records):
            nxt = records[i + 1]["Statistic"] if i + 1 < len(records) else None
            if r["Statistic"] == "Statistic":
                continue
            if nxt == "Statistic":
                group = r["Statistic"] if i > 0 else group
                continue
            rows.append({**r, "stat_group": group})
        sp = pd.DataFrame(rows, columns=["Statistic", "Per90", "Percentile", "stat_group"])
        sp["Per90"] = pd.to_numeric(sp["Per90"].astype(str).str.replace(r"[+%,]", "", regex=True), errors="coerce")
        sp["Percentile"] = pd.to_numeric(sp["Percentile"], errors="coerce")
        sp.insert(0, "StatGroup", sp.pop("stat_group"))
        sp.insert(0, "Versus", re.sub(r"vs\. ", "", versus))
        sp.insert(0, "Player", player_name)
        mins = []
        for f in pg.cssselect(".footer"):
            for s in f.cssselect("strong"):
                v = pd.to_numeric((s.text_content() or "").replace(" minutes", ""), errors="coerce")
                if not pd.isna(v) and v not in mins:
                    mins.append(v)
        sp["BasedOnMinutes"] = mins[0] if mins else np.nan
        sp["scouting_period"] = period
        frames.append(sp)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
