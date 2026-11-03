"""Carga de datos pre-scrapeados de FBref publicados en worldfootballR_data (load_fb.R).

Estas funciones no visitan FBref: descargan archivos ya preparados desde las
"releases" de GitHub del proyecto worldfootballR_data, por lo que son rápidas y
no tienen límites de peticiones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import _http
from .._utils import DATA_REPO_RAW, DATA_REPO_RELEASES, as_list, is_na, janitor_clean_name


def _announce(df: pd.DataFrame) -> None:
    ts = df.attrs.get("scrape_timestamp")
    if ts is not None:
        print(f"→ Data last updated {ts} UTC")


def _concat(urls):
    frames = [_http.file_reader(u) for u in urls]
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame()
    attrs = frames[0].attrs
    out = pd.concat(frames, ignore_index=True)
    out.attrs = attrs
    return out


def _filter_years(df, season_end_year):
    years = [y for y in as_list(season_end_year) if not is_na(y)]
    if years and "Season_End_Year" in df.columns:
        attrs = df.attrs
        df = df[df["Season_End_Year"].isin(years)].reset_index(drop=True)
        df.attrs = attrs
    return df


def load_match_results(country, gender, season_end_year, tier):
    """Resultados de partidos de ligas (versión precargada de ``fb_match_results``)."""
    urls = [f"{DATA_REPO_RELEASES}/match_results/{c}_match_results.rds" for c in as_list(country)]
    df = _concat(urls)
    if len(df) == 0:
        print("→ Data not loaded. Please check parameters.")
        return df
    attrs = df.attrs
    df = df[
        df["Country"].isin(as_list(country))
        & df["Gender"].isin(as_list(gender))
        & df["Season_End_Year"].isin(as_list(season_end_year))
        & df["Tier"].isin(as_list(tier))
    ].drop(columns=["Tier"]).reset_index(drop=True)
    df.attrs = attrs
    _announce(df)
    return df


def load_match_comp_results(comp_name):
    """Resultados de copas y torneos internacionales (p. ej. ``"Copa America"``, ``"FIFA World Cup"``)."""
    urls = [f"{DATA_REPO_RELEASES}/match_results_cups/{janitor_clean_name(c)}_match_results.rds"
            for c in as_list(comp_name)]
    df = _concat(urls)
    if len(df) == 0:
        print("→ Data not loaded. Please check parameters.")
        return df
    if "Tier" in df.columns:
        attrs = df.attrs
        df = df.drop(columns=["Tier"])
        df.attrs = attrs
    _announce(df)
    return df


def load_fb_big5_advanced_season_stats(season_end_year=np.nan, stat_type="standard", team_or_player="team"):
    """Versión precargada de ``fb_big5_advanced_season_stats``."""
    url = f"{DATA_REPO_RELEASES}/fb_big5_advanced_season_stats/big5_{team_or_player}_{stat_type}.rds"
    df = _http.file_reader(url)
    if len(df) == 0:
        print("→ Data not available. Check you have the correct stat_type or team_or_player.")
        return df
    df = _filter_years(df, season_end_year)
    _announce(df)
    return df


def _load_league_files(kind, country, gender, tier, extra="", season_end_year=np.nan):
    urls = []
    for c in as_list(country):
        for g in as_list(gender):
            for t in as_list(tier):
                urls.append(f"{DATA_REPO_RELEASES}/{kind}/{c}_{g}_{t}{extra}_{kind.replace('fb_', '')}.rds")
    df = _concat(urls)
    if len(df) == 0:
        print("→ Data not loaded. Please check parameters.")
        return df
    _announce(df)
    return _filter_years(df, season_end_year)


def load_fb_match_shooting(country, gender, tier, season_end_year=np.nan):
    """Tiros de partidos precargados (solo algunas ligas)."""
    return _load_league_files("fb_match_shooting", country, gender, tier, season_end_year=season_end_year)


def load_fb_match_summary(country, gender, tier, season_end_year=np.nan):
    """Resumen de eventos de partidos precargado (solo algunas ligas)."""
    return _load_league_files("fb_match_summary", country, gender, tier, season_end_year=season_end_year)


def load_fb_advanced_match_stats(country, gender, tier, stat_type, team_or_player, season_end_year=np.nan):
    """Estadísticas avanzadas por partido precargadas (solo algunas ligas)."""
    return _load_league_files("fb_advanced_match_stats", country, gender, tier,
                              extra=f"_{stat_type}_{team_or_player}", season_end_year=season_end_year)


def player_dictionary_mapping():
    """Tabla que relaciona jugadores de FBref con su URL de Transfermarkt (top 5 ligas desde 2017-18)."""
    url = f"{DATA_REPO_RAW}/raw-data/fbref-tm-player-mapping/output/fbref_to_tm_mapping.csv"
    return _http.read_csv_url(url)
