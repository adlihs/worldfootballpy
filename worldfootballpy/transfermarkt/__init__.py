"""Funciones para Transfermarkt (https://www.transfermarkt.com).

Usa siempre las URLs en inglés (``www.transfermarkt.com``): los selectores
dependen del texto de las cabeceras en inglés.
"""

from ._common import tm_meta
from ._league import (
    tm_expiring_contracts,
    tm_get_risk_of_suspension,
    tm_get_suspensions,
    tm_league_debutants,
    tm_league_injuries,
    tm_league_team_urls,
    tm_matchday_table,
    tm_team_player_urls,
    tm_team_staff_urls,
    tm_team_transfer_balances,
)
from ._players import (
    tm_each_team_player_market_val,
    tm_get_player_absence,
    tm_player_bio,
    tm_player_injury_history,
    tm_player_market_values,
    tm_player_transfer_history,
)
from ._teams import tm_squad_stats, tm_staff_job_history, tm_team_staff_history, tm_team_transfers

# alias obsoletos de worldfootballR
get_player_market_values = tm_player_market_values
player_transfer_history = tm_player_transfer_history

__all__ = [
    "tm_each_team_player_market_val", "tm_expiring_contracts", "tm_get_player_absence",
    "tm_get_risk_of_suspension", "tm_get_suspensions", "tm_league_debutants", "tm_league_injuries",
    "tm_league_team_urls", "tm_matchday_table", "tm_player_bio", "tm_player_injury_history",
    "tm_player_market_values", "tm_player_transfer_history", "tm_squad_stats", "tm_staff_job_history",
    "tm_team_player_urls", "tm_team_staff_history", "tm_team_staff_urls", "tm_team_transfer_balances",
    "tm_team_transfers", "tm_meta", "get_player_market_values", "player_transfer_history",
]
