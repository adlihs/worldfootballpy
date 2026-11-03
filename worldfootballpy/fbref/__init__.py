"""Funciones para FBref (https://fbref.com).

FBref pide no hacer más de ~10 peticiones por minuto; por eso todas las
funciones que visitan el sitio tienen ``time_pause`` (3 segundos por defecto,
como en worldfootballR). No lo bajes.
"""

import functools
import warnings

from ._load import (
    load_fb_advanced_match_stats,
    load_fb_big5_advanced_season_stats,
    load_fb_match_shooting,
    load_fb_match_summary,
    load_match_comp_results,
    load_match_results,
    player_dictionary_mapping,
)
from ._match import (
    _get_each_season_results,
    fb_advanced_match_stats,
    fb_match_lineups,
    fb_match_report,
    fb_match_results,
    fb_match_shooting,
    fb_match_summary,
    fb_match_urls,
)
from ._players import (
    fb_player_goal_logs,
    fb_player_info,
    fb_player_match_logs,
    fb_player_scouting_report,
)
from ._season import (
    fb_big5_advanced_season_stats,
    fb_league_stats,
    fb_player_season_stats,
    fb_season_team_stats,
)
from ._teams import (
    fb_squad_wages,
    fb_team_goal_logs,
    fb_team_match_log_stats,
    fb_team_match_results,
    fb_team_match_stats,
    fb_team_player_stats,
)
from ._urls import fb_league_urls, fb_player_urls, fb_teams_urls


def _deprecated(new_func, old_name):
    @functools.wraps(new_func)
    def wrapper(*args, **kwargs):
        warnings.warn(f"'{old_name}' está obsoleta; usa '{new_func.__name__}'.", DeprecationWarning, stacklevel=2)
        return new_func(*args, **kwargs)

    wrapper.__name__ = old_name
    return wrapper


# Nombres antiguos que worldfootballR mantiene como obsoletos
get_match_results = _deprecated(fb_match_results, "get_match_results")
get_match_urls = _deprecated(fb_match_urls, "get_match_urls")
get_match_report = _deprecated(fb_match_report, "get_match_report")
get_match_summary = _deprecated(fb_match_summary, "get_match_summary")
get_match_lineups = _deprecated(fb_match_lineups, "get_match_lineups")
get_match_shooting = _deprecated(fb_match_shooting, "get_match_shooting")
get_advanced_match_stats = _deprecated(fb_advanced_match_stats, "get_advanced_match_stats")
get_season_team_stats = _deprecated(fb_season_team_stats, "get_season_team_stats")
get_team_match_results = _deprecated(fb_team_match_results, "get_team_match_results")

__all__ = [
    "fb_advanced_match_stats", "fb_big5_advanced_season_stats", "fb_league_stats", "fb_league_urls",
    "fb_match_lineups", "fb_match_report", "fb_match_results", "fb_match_shooting", "fb_match_summary",
    "fb_match_urls", "fb_player_goal_logs", "fb_player_info", "fb_player_match_logs",
    "fb_player_scouting_report", "fb_player_season_stats", "fb_player_urls", "fb_season_team_stats",
    "fb_squad_wages", "fb_team_goal_logs", "fb_team_match_log_stats", "fb_team_match_results",
    "fb_team_match_stats", "fb_team_player_stats", "fb_teams_urls",
    "load_fb_advanced_match_stats", "load_fb_big5_advanced_season_stats", "load_fb_match_shooting",
    "load_fb_match_summary", "load_match_comp_results", "load_match_results", "player_dictionary_mapping",
    "get_match_results", "get_match_urls", "get_match_report", "get_match_summary", "get_match_lineups",
    "get_match_shooting", "get_advanced_match_stats", "get_season_team_stats", "get_team_match_results",
]
