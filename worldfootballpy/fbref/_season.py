"""Estadísticas de temporada de FBref.

Traducción de get_season_team_stats.R, fb_big5_advanced_season.R,
fb_league_stats.R y get_season_player_stats.R.
"""

from __future__ import annotations

import os
import re

import lxml.etree
import lxml.html
import numpy as np
import pandas as pd

from .. import _http
from .._table import first_row_as_char, html_table
from .._utils import (
    FBREF,
    all_competitions,
    as_list,
    clean_advanced_stat_table,
    clean_numeric,
    clean_player_season_stats,
    is_na,
    numeric_cols,
    progress,
    rename_fb_cols,
    squish,
)


def _team_opponent_order(stat_df: pd.DataFrame) -> pd.DataFrame:
    is_opp = stat_df["Squad"].astype(str).str.contains("vs ", regex=False)
    stat_df = stat_df.copy()
    stat_df["Team_or_Opponent"] = np.where(is_opp, "opponent", "team")
    return pd.concat([stat_df[~is_opp], stat_df[is_opp]], ignore_index=True)


# ----------------------------------------------------------------------------
# fb_season_team_stats
# ----------------------------------------------------------------------------

_SEASON_TEAM_TYPES = {
    "standard": "stats_squads_standard",
    "keeper": "stats_squads_keeper",
    "keeper_adv": "stats_squads_keeper_adv",
    "shooting": "stats_squads_shooting",
    "passing": "stats_squads_passing",
    "passing_types": "stats_squads_passing_types",
    "goal_shot_creation": "stats_squads_gca",
    "defense": "stats_squads_defense",
    "possession": "stats_squads_possession",
    "playing_time": "stats_squads_playing_time",
    "misc": "stats_squads_misc",
}


def fb_season_team_stats(country, gender, season_end_year, tier, stat_type, time_pause=3):
    """Estadísticas de equipo (y de rivales) de una liga y temporada(s).

    ``stat_type``: ``"league_table"``, ``"league_table_home_away"``, ``"standard"``,
    ``"keeper"``, ``"keeper_adv"``, ``"shooting"``, ``"passing"``, ``"passing_types"``,
    ``"goal_shot_creation"``, ``"defense"``, ``"possession"``, ``"playing_time"``, ``"misc"``.
    """
    seasons = all_competitions()
    filt = seasons[seasons["competition_type"].astype(str).str.contains("Leagues", na=False)]
    filt = filt[
        filt["country"].isin(as_list(country))
        & filt["gender"].isin(as_list(gender))
        & filt["season_end_year"].isin(as_list(season_end_year))
        & filt["tier"].isin(as_list(tier))
    ].sort_values("season_end_year", kind="stable")
    urls = list(dict.fromkeys(filt["seasons_urls"].dropna()))

    frames = []
    for url in progress(urls, "fb_season_team_stats"):
        _http.sleep(time_pause)
        page = _http.load_page(url)
        try:
            stat_df = _season_team_stat_page(page, stat_type)
        except Exception:
            stat_df = pd.DataFrame()
        if stat_df is None or len(stat_df) == 0:
            print(f"NOTE: Stat Type '{stat_type}' is not found for this league season. Check {url} to see if it exists.")
            continue
        stat_df.columns = [c.replace("+", "_plus_") for c in stat_df.columns]
        stat_df = _team_opponent_order(stat_df)
        stat_df.insert(0, "season_url", url)
        front = ["season_url", "Squad", "Team_or_Opponent"]
        stat_df = stat_df[front + [c for c in stat_df.columns if c not in front]]
        meta = seasons[["competition_name", "gender", "country", "season_end_year", "seasons_urls"]].rename(
            columns={"competition_name": "Competition_Name", "gender": "Gender", "country": "Country",
                     "season_end_year": "Season_End_Year"})
        merged = meta.merge(stat_df, left_on="seasons_urls", right_on="season_url", how="inner")
        merged = merged.drop(columns=["seasons_urls", "season_url"])
        merged = merged[merged["Squad"].notna()]
        merged = merged.sort_values(
            ["Country", "Competition_Name", "Gender", "Season_End_Year", "Team_or_Opponent", "Squad"],
            ascending=[True, True, True, True, False, True], kind="stable",
        ).drop_duplicates()
        frames.append(merged)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _season_team_stat_page(page, stat_type):
    standings = page.cssselect("table")
    holders = page.cssselect(".stats_table")
    ids = [h.get("id") or "" for h in holders]
    has_conf = any(re.search("Conference", i, flags=re.I) for i in ids)
    h2s = [h for sc in page.cssselect(".section_content") for h in sc.cssselect("h2")]

    if stat_type == "league_table":
        if has_conf:
            d1 = html_table(standings[0])
            d1["Conference"] = squish(h2s[0].text_content()) if h2s else np.nan
            d2 = html_table(standings[2])
            d2["Conference"] = squish(h2s[2].text_content()) if len(h2s) > 2 else np.nan
            df = pd.concat([d1, d2], ignore_index=True)
        else:
            df = html_table(standings[0])
        if "Attendance" in df.columns:
            df["Attendance"] = clean_numeric(df["Attendance"].astype(str))
        return df

    if stat_type == "league_table_home_away":
        if has_conf:
            d1 = html_table(standings[1])
            d1["Conference"] = squish(h2s[1].text_content()) if len(h2s) > 1 else np.nan
            d2 = html_table(standings[3])
            d2["Conference"] = squish(h2s[3].text_content()) if len(h2s) > 3 else np.nan
            df = pd.concat([d1, d2], ignore_index=True)
            df.loc[0, "Conference"] = "Conference"
        else:
            sel = [s for s, i in zip(holders, ids) if "home_away" in i]
            df = html_table(sel[0])
        names = [f"{a}_{b}" for a, b in zip(first_row_as_char(df), df.columns)]
        names = [re.sub(r"/", "_per_", re.sub(r"_Var", "", re.sub(r"\..*", "", n))) for n in names]
        df = df.iloc[1:].copy()
        df.columns = names
        df = df[df["Rk"].astype(str) != "Rk"]
        if "Conference_Conference" in df.columns:
            df = df.rename(columns={"Conference_Conference": "Conference"})
        return numeric_cols(df.reset_index(drop=True), ["Squad", "Conference"])

    if stat_type not in _SEASON_TEAM_TYPES:
        raise ValueError(f"stat_type no válido: {stat_type}")
    prefix = _SEASON_TEAM_TYPES[stat_type]
    parts = []
    for suffix in ("_for", "_against"):
        sel = [h for h, i in zip(holders, ids) if (prefix + suffix) in i]
        if sel:
            try:
                parts.append(clean_advanced_stat_table(sel[0]))
            except Exception:
                pass
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ----------------------------------------------------------------------------
# fb_big5_advanced_season_stats
# ----------------------------------------------------------------------------

_BIG5_TYPES = ["standard", "shooting", "passing", "passing_types", "gca", "defense", "possession",
               "playing_time", "misc", "keepers", "keepers_adv"]


def _big5_names(df, stat_type):
    names = [f"{a}_{b}" for a, b in zip(first_row_as_char(df), df.columns)]
    if stat_type == "playingtime":
        steps = [(r"\..[0-9]+", ""), (r"\.[0-9]+", ""), (r"_Var", ""), (r"# Pl", "Num_Players"),
                 (r"%", "_percent"), (r"_Performance", ""), (r"1/3", "Final_Third"), (r"/", "_per_"),
                 (r"-", "_minus_"), (r"90s", "Mins_Per_90"), (r"\+", "plus")]
    else:
        steps = [(r"\..*", ""), (r"_Var", ""), (r"# Pl", "Num_Players"), (r"%", "_percent"),
                 (r"_Performance", ""), (r"1/3", "Final_Third"), (r"/", "_per_"), (r"-", "_minus_"),
                 (r"90s", "Mins_Per_90")]
    out = []
    for n in names:
        for p, r in steps:
            n = re.sub(p, r, n)
        out.append(n)
    return out


def fb_big5_advanced_season_stats(season_end_year, stat_type, team_or_player, time_pause=3):
    """Estadísticas de temporada de las 5 grandes ligas europeas, por equipo o jugador.

    ``stat_type``: ``"standard"``, ``"shooting"``, ``"passing"``, ``"passing_types"``, ``"gca"``,
    ``"defense"``, ``"possession"``, ``"playing_time"``, ``"misc"``, ``"keepers"``, ``"keepers_adv"``.
    """
    if stat_type not in _BIG5_TYPES:
        raise ValueError("check stat type")
    seasons = all_competitions()
    big5 = seasons[seasons["competition_type"].astype(str).str.contains("Big 5 European Leagues", na=False)]
    big5 = big5[big5["season_end_year"].isin(as_list(season_end_year))].sort_values("season_end_year", kind="stable")
    urls = list(dict.fromkeys(big5["seasons_urls"]))
    st = {"standard": "stats", "playing_time": "playingtime", "keepers_adv": "keepersadv"}.get(stat_type, stat_type)

    frames = []
    for season_url in progress(urls, "fb_big5_advanced_season_stats"):
        _http.sleep(time_pause)
        start, end = season_url.rsplit("/", 1)
        part = "squads" if team_or_player == "team" else "players"
        page = _http.load_page(f"{start}/{st}/{part}/{end}")
        tables = [t for c in page.cssselect(".table_container") for t in c.cssselect("table")]
        if team_or_player == "player":
            df = html_table(tables[0])
        else:
            df = pd.concat([html_table(tables[0]), html_table(tables[1])], ignore_index=True)
        names = _big5_names(df, st)
        df = df.iloc[1:].copy()
        df.columns = names
        df = df.reset_index(drop=True)

        row_urls = []
        for t in tables:
            for tb in t.cssselect("tbody"):
                for tr in tb.cssselect("tr"):
                    a = tr.cssselect("td a")
                    row_urls.append(FBREF + a[0].get("href") if a and a[0].get("href") else FBREF + "NA")

        if team_or_player == "player":
            df["Url"] = (row_urls + [np.nan] * len(df))[: len(df)]
            df = df[df["Rk"].astype(str) != "Rk"].drop(columns=["Rk"])
            df = df.drop(columns=[c for c in ["Matches"] if c in df.columns])
            non_num = ["Squad", "Player", "Nation", "Pos", "Comp", "Age", "Url"]
            chr_vars = ["Nation", "Comp"]
        else:
            df = df[df["Rk"].astype(str) != "Rk"].drop(columns=["Rk"]).reset_index(drop=True)
            df["Url"] = (row_urls + [np.nan] * len(df))[: len(df)]
            non_num = ["Squad", "Comp", "Url"]
            chr_vars = ["Comp"]
        df = numeric_cols(df.reset_index(drop=True), non_num)
        for c in chr_vars:
            if c in df.columns:
                df[c] = df[c].astype(object).map(lambda v: re.sub(r"^\S* ", "", v) if isinstance(v, str) else v)

        df = _team_opponent_order(df)
        df["season_url"] = season_url
        df["Squad"] = df["Squad"].astype(str).str.replace("vs ", "", regex=False)
        front = ["season_url", "Squad", "Comp", "Team_or_Opponent"]
        df = df[front + [c for c in df.columns if c not in front]]
        meta = seasons[["season_end_year", "seasons_urls"]].rename(columns={"season_end_year": "Season_End_Year"})
        df = meta.merge(df, left_on="seasons_urls", right_on="season_url", how="inner")
        df = df.drop(columns=["seasons_urls", "season_url"])
        df = df[df["Squad"].notna()]
        df = df.sort_values(["Season_End_Year", "Squad", "Team_or_Opponent"],
                            ascending=[True, True, False], kind="stable")
        if team_or_player == "player":
            df = df.drop(columns=["Team_or_Opponent"])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# fb_league_stats
# ----------------------------------------------------------------------------

_LEAGUE_TYPES = ["standard", "shooting", "passing", "passing_types", "gca", "defense", "possession",
                 "playing_time", "misc", "keepers", "keepers_adv"]


def _find_in_comments(page, element_id):
    """FBref esconde muchas tablas dentro de comentarios HTML; las buscamos ahí."""
    found = page.xpath(f'//*[@id="{element_id}"]')
    if found:
        return found[0]
    for comment in page.iter(lxml.etree.Comment):
        txt = comment.text or ""
        if element_id in txt:
            frag = lxml.html.fromstring(f"<div>{txt}</div>")
            hit = frag.xpath(f'//*[@id="{element_id}"]')
            if hit:
                return hit[0]
    return None


def _single_league_stats(url, team_or_player, stat_type):
    page = _http.load_page(url)
    if team_or_player == "team":
        tables = page.xpath("//table")
        if len(tables) != 2:
            print(f"Did not find the expected number of tables on the page (2). Found {len(tables)}.")
            return pd.DataFrame()
        out = []
        for i, t in enumerate(tables):
            df = rename_fb_cols(html_table(t))
            df.insert(0, "Team_or_Opponent", "team" if i == 0 else "opponent")
            out.append(df)
        return pd.concat(out, ignore_index=True)

    st = stat_type.replace("keepers", "keeper")
    element = _find_in_comments(page, f"div_stats_{st}")
    if element is None:
        return pd.DataFrame()
    table = element if element.tag == "table" else (element.cssselect("table") or [None])[0]
    if table is None:
        return pd.DataFrame()
    df = rename_fb_cols(html_table(table))
    df = df[df["Rk"].astype(str) != "Rk"].reset_index(drop=True)
    hrefs = [a.get("href") for a in table.xpath(".//tbody/tr/td[@data-stat='player']/a")]
    pos = list(df.columns).index("Player") + 1 if "Player" in df.columns else len(df.columns)
    df.insert(pos, "Player_Href", (hrefs + [np.nan] * len(df))[: len(df)])
    for c in df.columns:
        conv = pd.to_numeric(df[c], errors="coerce")
        orig = df[c]
        non_empty = orig.notna() & (orig.astype(str).str.strip() != "")
        if non_empty.any() and conv[non_empty].notna().all():
            df[c] = conv
    return df


def fb_league_stats(country, gender, season_end_year, tier="1st", non_dom_league_url=np.nan,
                    stat_type="standard", team_or_player="team", time_pause=3):
    """Estadísticas de una liga (equipos o jugadores) por temporada.

    A diferencia de la versión de R (que necesita Chrome con ``read_html_live``),
    aquí la tabla de jugadores se lee directamente de los comentarios HTML de FBref.
    """
    if stat_type not in _LEAGUE_TYPES:
        raise ValueError(f"stat_type debe ser uno de {_LEAGUE_TYPES}")
    if team_or_player not in ("team", "player"):
        raise ValueError("team_or_player debe ser 'team' o 'player'")
    seasons = all_competitions()
    s = seasons[
        seasons["country"].isin(as_list(country))
        & seasons["gender"].isin(as_list(gender))
        & seasons["season_end_year"].isin(as_list(season_end_year))
        & seasons["tier"].isin(as_list(tier))
    ]
    if is_na(non_dom_league_url):
        s = s[s["competition_type"].astype(str).str.contains("Leagues", na=False)]
    else:
        s = s[s["comp_url"].isin(as_list(non_dom_league_url))]
    if len(s) == 0:
        raise ValueError("Could not find any URLs matching input parameters")
    st = {"standard": "stats", "keepers_adv": "keepersadv", "playing_time": "playingtime"}.get(stat_type, stat_type)
    s = s.drop_duplicates(subset=["seasons_urls"])
    urls = []
    for _, row in s.iterrows():
        comp_url = row["comp_url"]
        season = str(row["seasons"])
        base = os.path.dirname(comp_url).replace("history", season)
        name = season + "-" + os.path.basename(comp_url).replace("Seasons", "Stats")
        urls.append(f"{base}/{st}/{name}")

    frames = []
    for i, url in enumerate(progress(urls, "fb_league_stats")):
        if i > 0:
            _http.sleep(time_pause)
        res = pd.DataFrame()
        for _attempt in range(3):
            try:
                res = _single_league_stats(url, team_or_player, stat_type)
                break
            except Exception as e:  # reintento con espera, como purrr::insistently
                last = e
                _http.sleep(2 ** _attempt)
        else:
            print(f"Error en {url}: {last}")
        res["url"] = url
        frames.append(res)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ----------------------------------------------------------------------------
# fb_player_season_stats
# ----------------------------------------------------------------------------

_PLAYER_SEASON_TYPES = ["standard", "shooting", "passing", "passing_types", "gca", "defense",
                        "possession", "playing_time", "misc", "keeper", "keeper_adv"]


def _table_ids(tables):
    return [t.get("id") or "" for t in tables]


def fb_player_season_stats(player_url, stat_type, national=False, time_pause=3):
    """Estadísticas por temporada de uno o varios jugadores (todas las competiciones).

    ``national=True`` devuelve sus estadísticas con la selección nacional.
    """
    urls = as_list(player_url)
    types = as_list(stat_type)
    if len(types) == 1:
        types = types * len(urls)
    frames = []
    for url, st in progress(list(zip(urls, types)), "fb_player_season_stats"):
        _http.sleep(time_pause)
        if st not in _PLAYER_SEASON_TYPES:
            raise ValueError("check stat type")
        page = _http.load_page(url)
        h1 = page.cssselect("h1")
        player_name = squish(h1[0].text_content()) if h1 else np.nan
        filters = [a.get("href") for f in page.cssselect(".filter") for a in f.cssselect("a") if a.get("href")]
        stats_string = "National-Team" if national else "All-Compe"
        stat_df = pd.DataFrame()

        def pick(tables, ids, pattern):
            sel = [t for t, i in zip(tables, ids) if re.search(pattern, i)]
            if not sel:
                return pd.DataFrame()
            try:
                return clean_player_season_stats(sel[0])
            except Exception:
                return pd.DataFrame()

        if any(stats_string in f for f in filters):
            comp_url = FBREF + [f for f in filters if stats_string in f][0]
            _http.sleep(time_pause)
            comp_page = _http.load_page(comp_url)
            tables = [t for c in comp_page.cssselect(".table_container") for t in c.cssselect("table")]
            ids = _table_ids(tables)
            exp = [i for i, x in enumerate(ids) if "_expanded" in x]
            if not exp:
                cs = "_nat_tm" if national else "_dom_lg"
                keep = [i for i, x in enumerate(ids) if cs in x]
                tables = [tables[i] for i in keep]
                ids = [ids[i] for i in keep]
                stat_df = pick(tables, ids, f"stats_{st}{cs}")
            else:
                tables = [tables[i] for i in exp]
                ids = [ids[i] for i in exp]
                stat_df = pick(tables, ids, f"stats_{st}_expanded")
        elif stats_string == "All-Compe":
            tables = [t for c in page.cssselect(".table_container") for t in c.cssselect("table")]
            if not tables:
                stat_df = pd.DataFrame({"player_name": [player_name], "player_url": [url], "Country": [np.nan]})
            else:
                ids = _table_ids(tables)
                keep = [i for i, x in enumerate(ids) if "_dom_" in x]
                tables = [tables[i] for i in keep]
                ids = [ids[i] for i in keep]
                stat_df = pick(tables, ids, f"stats_{st}")

        if len(stat_df) == 0:
            msg = f"{st} data not available for: {url}"
            print(("National " + msg) if national else msg)
            continue
        if "player_name" not in stat_df.columns:
            mask = stat_df.apply(lambda r: any((v != "" and not is_na(v)) for v in r), axis=1)
            stat_df = stat_df[mask].copy()
            stat_df.insert(0, "player_url", url)
            stat_df.insert(0, "player_name", player_name)
        frames.append(stat_df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


__all__ = ["fb_season_team_stats", "fb_big5_advanced_season_stats", "fb_league_stats",
           "fb_player_season_stats"]
