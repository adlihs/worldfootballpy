"""URLs de ligas, equipos y jugadores en FBref (worldfootballr_helpers.R)."""

from __future__ import annotations

from .. import _http
from .._utils import FBREF, all_competitions, as_list


def fb_league_urls(country, gender, season_end_year, tier="1st"):
    """URLs de las temporadas de liga para un país, género, temporada y nivel."""
    s = all_competitions()
    s = s[
        s["country"].isin(as_list(country))
        & s["gender"].isin(as_list(gender))
        & s["season_end_year"].isin(as_list(season_end_year))
        & s["tier"].isin(as_list(tier))
    ]
    return list(dict.fromkeys(s["seasons_urls"]))


def fb_teams_urls(league_url, time_pause=3):
    """URLs de todos los equipos de una liga/temporada."""
    _http.sleep(time_pause)
    page = _http.load_page(league_url)
    hrefs = [a.get("href") for t in page.cssselect(".stats_table") for a in t.cssselect("img + a")]
    return [FBREF + h for h in dict.fromkeys(hrefs) if h]


def fb_player_urls(team_url, time_pause=3):
    """URLs de todos los jugadores de un equipo."""
    _http.sleep(time_pause)
    page = _http.load_page(team_url)
    return [FBREF + (a.get("href") or "") for a in page.cssselect("#all_stats_standard th a")]
