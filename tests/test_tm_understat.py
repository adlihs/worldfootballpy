"""Pruebas de Transfermarkt y Understat con datos simulados (sin red)."""

import worldfootballpy as wf
from worldfootballpy import _http

# Funciones exportadas por worldfootballR 0.6.8 (NAMESPACE), sin las internas
R_EXPORTS = """
fb_advanced_match_stats fb_big5_advanced_season_stats fb_league_stats fb_league_urls fb_match_lineups
fb_match_report fb_match_results fb_match_shooting fb_match_summary fb_match_urls fb_player_goal_logs
fb_player_info fb_player_match_logs fb_player_scouting_report fb_player_season_stats fb_player_urls
fb_season_team_stats fb_squad_wages fb_team_goal_logs fb_team_match_log_stats fb_team_match_results
fb_team_match_stats fb_team_player_stats fb_teams_urls get_advanced_match_stats get_match_lineups
get_match_report get_match_results get_match_shooting get_match_summary get_match_urls
get_player_market_values get_season_team_stats get_team_match_results load_fb_advanced_match_stats
load_fb_big5_advanced_season_stats load_fb_match_shooting load_fb_match_summary load_match_comp_results
load_match_results load_understat_league_shots player_dictionary_mapping player_transfer_history
tm_each_team_player_market_val tm_expiring_contracts tm_get_player_absence tm_get_risk_of_suspension
tm_get_suspensions tm_league_debutants tm_league_injuries tm_league_team_urls tm_matchday_table
tm_player_bio tm_player_injury_history tm_player_market_values tm_player_transfer_history tm_squad_stats
tm_staff_job_history tm_team_player_urls tm_team_staff_history tm_team_staff_urls
tm_team_transfer_balances tm_team_transfers understat_available_teams understat_league_match_results
understat_league_season_shots understat_match_players understat_match_shots understat_match_stats
understat_player_shots understat_team_meta understat_team_players_stats understat_team_season_shots
understat_team_stats_breakdown
""".split()


def test_all_r_functions_exist():
    missing = [f for f in R_EXPORTS if not callable(getattr(wf, f, None))]
    assert missing == []


SQUAD = """
<html><body>
<h1 class="data-header__headline-wrapper data-header__headline-wrapper--oswald">Deportivo Saprissa</h1>
<div class="data-header__club"><a href="/x">Primera División</a></div>
<div class="data-header__content"><a href="/y"><img title="Costa Rica" src="f.png"></a></div>
<div id="yw1"><table class="items"><thead><tr>
<th>#</th><th>Player</th><th>Date of birth/Age</th><th>Nat.</th><th>Height</th><th>Foot</th><th>Joined</th>
<th>Signed from</th><th>Contract</th><th>Market value</th></tr></thead>
<tbody><tr>
<td><div class="rn_nummer">1</div></td>
<td class="posrela"><table class="inline-table"><tr><td><a href="/kevin-chamorro/profil/spieler/1">Kevin Chamorro</a></td></tr>
<tr><td>Goalkeeper</td></tr></table></td>
<td class="zentriert">Apr 8, 2000 (26)</td>
<td class="zentriert"><img class="flaggenrahmen" title="Costa Rica"></td>
<td class="zentriert">1,85m</td><td class="zentriert">right</td><td class="zentriert">Jul 1, 2022</td>
<td class="zentriert"><a href="/club"><img alt="Municipal Grecia"></a></td>
<td class="zentriert">Jun 30, 2027</td><td class="rechts hauptlink">€500k</td>
</tr></tbody></table></div></body></html>
"""


def test_tm_each_team_player_market_val(fake_web):
    pages, _ = fake_web
    url = "https://www.transfermarkt.com/deportivo-saprissa/startseite/verein/1/saison_id/2025"
    pages["https://www.transfermarkt.com/deportivo-saprissa/kader/verein/1/saison_id/2025/plus/1"] = SQUAD
    df = wf.tm_each_team_player_market_val(url, time_pause=0)
    r = df.iloc[0]
    assert r["squad"] == "Deportivo Saprissa"
    assert r["comp_name"] == "Primera División" and r["country"] == "Costa Rica"
    assert r["season_start_year"] == 2025
    assert r["player_name"] == "Kevin Chamorro" and r["player_position"] == "Goalkeeper"
    assert r["player_age"] == 26 and str(r["player_dob"].date()) == "2000-04-08"
    assert r["player_height_mtrs"] == 1.85 and r["player_foot"] == "right"
    assert r["date_joined"] == "2022-07-01" and r["contract_expiry"] == "2027-06-30"
    assert r["joined_from"] == "Municipal Grecia"
    assert r["player_market_value_euro"] == 500_000
    assert r["player_url"] == "https://www.transfermarkt.com/kevin-chamorro/profil/spieler/1"


def _js(obj):
    import json

    raw = json.dumps(obj)
    return "".join(f"\\x{ord(c):02X}" if c in '"{}[]:' else c for c in raw)


class _Resp:
    def __init__(self, text):
        self.text = text
        self.content = text.encode()

    def json(self):
        import json

        return json.loads(self.text)


def test_understat_league_results_and_players(monkeypatch):
    dates = [
        {"id": "100", "isResult": True, "h": {"id": "1", "title": "Arsenal", "short_title": "ARS"},
         "a": {"id": "2", "title": "Chelsea", "short_title": "CHE"}, "goals": {"h": "2", "a": "1"},
         "xG": {"h": "1.8", "a": "0.9"}, "datetime": "2024-08-17 15:00:00",
         "forecast": {"w": "0.6", "d": "0.25", "l": "0.15"}},
        {"id": "101", "isResult": False, "h": {"id": "3", "title": "Fulham", "short_title": "FUL"},
         "a": {"id": "4", "title": "Spurs", "short_title": "TOT"}, "goals": {"h": None, "a": None},
         "xG": {"h": None, "a": None}, "datetime": "2025-05-25 15:00:00", "forecast": {}},
    ]
    rosters = {"h": {"1": {"id": "1", "team_id": "1", "h_a": "h", "player_id": "77", "player": "Bukayo Saka",
                           "position": "AMR", "positionOrder": "13", "time": "90", "goals": "1", "own_goals": "0",
                           "shots": "3", "xG": "0.8", "yellow_card": "0", "red_card": "0", "roster_in": "0",
                           "roster_out": "0", "key_passes": "2", "assists": "0", "xA": "0.3", "xGChain": "1.1",
                           "xGBuildup": "0.2"}},
               "a": {}}
    pages = {
        "https://understat.com/league/EPL/2024":
            '<select name="season"><option value="2024" selected>2024/2025</option></select>'
            f"<script>var datesData = JSON.parse('{_js(dates)}');</script>",
        "https://understat.com/match/100": f"<script>var rostersData\t= JSON.parse('{_js(rosters)}');</script>",
    }
    monkeypatch.setattr(_http, "get", lambda url, **kw: _Resp(pages[url]))

    res = wf.understat_league_match_results("EPL", 2024)
    assert len(res) == 1
    r = res.iloc[0]
    assert (r["league"], r["season"], r["home_team"], r["away_abbr"]) == ("EPL", "2024/2025", "Arsenal", "CHE")
    assert (r["home_goals"], r["away_xG"], r["forecast_win"]) == (2, 0.9, 0.6)

    pl = wf.understat_match_players("https://understat.com/match/100")
    assert pl.loc[0, "player"] == "Bukayo Saka" and pl.loc[0, "xG"] == 0.8 and pl.loc[0, "match_id"] == 100
