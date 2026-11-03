"""Pruebas de funciones de FBref con HTML simulado (sin red)."""

import pandas as pd

import worldfootballpy as wf
from tests.conftest import competitions, competitions_row
from worldfootballpy._utils import ALL_COMPETITIONS_CSV

# Nombres reales del archivo big5_team_standard.rds generado por worldfootballR
R_BIG5_TEAM_STANDARD = {
    "Season_End_Year", "Squad", "Comp", "Team_or_Opponent", "Num_Players", "Age", "Poss", "MP_Playing",
    "Starts_Playing", "Min_Playing", "Mins_Per_90_Playing", "Gls", "Ast", "G+A", "G_minus_PK", "PK", "PKatt",
    "CrdY", "CrdR", "PrgC_Progression", "PrgP_Progression", "Gls_Per", "Ast_Per", "G+A_Per", "G_minus_PK_Per",
    "G+A_minus_PK_Per", "xG_Expected", "npxG_Expected", "xAG_Expected", "npxG+xAG_Expected", "xG_Per", "xAG_Per",
    "xG+xAG_Per", "npxG_Per", "npxG+xAG_Per", "Url",
}

_OVER = ('<tr class="over_header"><th colspan="6"></th><th colspan="4">Playing Time</th>'
         '<th colspan="8">Performance</th><th colspan="4">Expected</th><th colspan="2">Progression</th>'
         '<th colspan="10">Per 90 Minutes</th></tr>')
_HEAD = ("<tr>" + "".join(f"<th>{h}</th>" for h in [
    "Rk", "Squad", "Comp", "# Pl", "Age", "Poss", "MP", "Starts", "Min", "90s", "Gls", "Ast", "G+A", "G-PK", "PK",
    "PKatt", "CrdY", "CrdR", "xG", "npxG", "xAG", "npxG+xAG", "PrgC", "PrgP", "Gls", "Ast", "G+A", "G-PK", "G+A-PK",
    "xG", "xAG", "xG+xAG", "npxG", "npxG+xAG"]) + "</tr>")


def _row(rk, squad, href):
    vals = ["eng Premier League", "25", "27.1", "60.2", "38", "418", "3,420", "38.0"] + ["10"] * 14 + ["1.0"] * 10
    tds = "".join(f"<td>{v}</td>" for v in vals)
    return f'<tr><th>{rk}</th><td><a href="{href}">{squad}</a></td>{tds}</tr>'


def _big5_page():
    t1 = f'<table id="stats_teams_standard_for"><thead>{_OVER}{_HEAD}</thead><tbody>{_row(1, "Arsenal", "/en/squads/18bb7c10/Arsenal-Stats")}</tbody></table>'
    t2 = f'<table id="stats_teams_standard_against"><thead>{_OVER}{_HEAD}</thead><tbody>{_row(1, "vs Arsenal", "/en/squads/18bb7c10/Arsenal-Stats")}</tbody></table>'
    return f'<html><body><div class="table_container">{t1}</div><div class="table_container">{t2}</div></body></html>'


def test_big5_team_columns_match_r(fake_web):
    pages, csvs = fake_web
    season_url = "https://fbref.com/en/comps/Big5/2023-2024/2023-2024-Big-5-European-Leagues-Stats"
    csvs[ALL_COMPETITIONS_CSV] = competitions(competitions_row(
        competition_type="Big 5 European Leagues", seasons_urls=season_url, season_end_year=2024))
    pages["https://fbref.com/en/comps/Big5/2023-2024/stats/squads/2023-2024-Big-5-European-Leagues-Stats"] = _big5_page()

    df = wf.fb_big5_advanced_season_stats(2024, "standard", "team")
    assert set(df.columns) == R_BIG5_TEAM_STANDARD
    assert df["Team_or_Opponent"].tolist() == ["team", "opponent"]
    assert df["Squad"].tolist() == ["Arsenal", "Arsenal"]
    assert df["Comp"].iloc[0] == "Premier League"
    assert df["Min_Playing"].iloc[0] == 3420
    assert df["Url"].iloc[0] == "https://fbref.com/en/squads/18bb7c10/Arsenal-Stats"


FIXTURES = """
<html><body><h2><span>2023-2024 Premier League Scores &amp; Fixtures</span></h2>
<table class="stats_table"><thead><tr>
<th>Wk</th><th>Day</th><th>Date</th><th>Time</th><th>Home</th><th>xG</th><th>Score</th><th>xG</th><th>Away</th>
<th>Attendance</th><th>Venue</th><th>Referee</th><th>Match Report</th><th>Notes</th></tr></thead>
<tbody>
<tr><th>1</th><td>Fri</td><td>2023-08-11</td><td>20:00</td><td>Burnley</td><td>0.3</td><td>0–3</td><td>1.9</td>
<td>Manchester City</td><td>21,572</td><td>Turf Moor</td><td>Craig Pawson</td>
<td data-stat="match_report"><a href="/en/matches/3a6836b4/Burnley-Manchester-City">Match Report</a></td><td></td></tr>
<tr class="spacer partial_table"><th></th><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr class="thead"><th>Wk</th><td>Day</td><td>Date</td><td>Time</td><td>Home</td><td>xG</td><td>Score</td><td>xG</td><td>Away</td><td>Attendance</td><td>Venue</td><td>Referee</td><td>Match Report</td><td>Notes</td></tr>
<tr><th>1</th><td>Sat</td><td>2023-08-12</td><td>12:30</td><td>Arsenal</td><td>0.8</td><td>2–1</td><td>1.2</td>
<td>Nott'ham Forest</td><td>59,984</td><td>Emirates Stadium</td><td>Michael Oliver</td>
<td data-stat="match_report"><a href="/en/matches/bdbc722e/Arsenal-Nottingham-Forest">Match Report</a></td><td></td></tr>
</tbody></table></body></html>
"""


def test_fb_match_results(fake_web):
    pages, csvs = fake_web
    row = competitions_row()
    csvs[ALL_COMPETITIONS_CSV] = competitions(row)
    pages[row["fixtures_url"]] = FIXTURES
    df = wf.fb_match_results("ENG", "M", 2024, "1st")
    expected = ["Competition_Name", "Gender", "Country", "Season_End_Year", "Round", "Wk", "Day", "Date", "Time",
                "Home", "HomeGoals", "Home_xG", "Away", "AwayGoals", "Away_xG", "Attendance", "Venue", "Referee",
                "Notes", "MatchURL"]
    assert list(df.columns) == expected
    assert len(df) == 2
    first = df.iloc[0]
    assert (first["Home"], first["HomeGoals"], first["AwayGoals"]) == ("Burnley", 0, 3)
    assert first["Home_xG"] == 0.3 and first["Attendance"] == 21572
    assert first["MatchURL"] == "https://fbref.com/en/matches/3a6836b4/Burnley-Manchester-City"
    assert df.iloc[1]["MatchURL"].endswith("Arsenal-Nottingham-Forest")
    assert pd.api.types.is_datetime64_any_dtype(df["Date"])


MATCH = """
<html><body><div class="langs"><a class="en" href="https://fbref.com/en/matches/x/A-B">EN</a></div>
<div id="content"><h1>Arsenal vs. Chelsea Match Report</h1>
<div><a href="/en/comps/9">Premier League</a> (Matchweek 5)</div>
<div class="scorebox">
 <div><div><div class="logo"></div><strong><a href="/en/squads/a">Arsenal</a></strong></div>
  <div class="scores"><div class="score">2</div><div class="score_xg">1.8</div></div></div>
 <div><div><div class="logo"></div><strong><a href="/en/squads/c">Chelsea</a></strong></div>
  <div class="scores"><div class="score">1</div><div class="score_xg">0.9</div></div></div>
 <div class="scorebox_meta"><span class="venuetime" data-venue-date="2023-10-21"></span></div>
</div>
<div class="cards"><span class="yellow_card"></span><span class="yellow_card"></span></div>
<div class="cards"><span class="red_card"></span></div>
<div id="events_wrap">
 <div class="event a">12&amp;rsquor; Bukayo Saka 1:0 — Goal</div>
 <div class="event b">55&rsquor; Cole Palmer 1:1 — Penalty Kick</div>
 <div class="event a">90+2’ Declan Rice 2:1 — Goal</div>
</div></div></body></html>
"""


def test_fb_match_report_and_summary(fake_web):
    pages, _ = fake_web
    url = "https://fbref.com/en/matches/x/A-B"
    pages[url] = MATCH
    rep = wf.fb_match_report(url)
    r = rep.iloc[0]
    assert (r["Home_Team"], r["Away_Team"]) == ("Arsenal", "Chelsea")
    assert (r["Home_Score"], r["Away_Score"], r["Home_xG"]) == (2, 1, 1.8)
    assert (r["Home_Yellow_Cards"], r["Away_Red_Cards"]) == (2, 1)
    assert r["Match_Date"] == "2023-10-21"

    summ = wf.fb_match_summary(url)
    assert len(summ) == 3
    assert summ["Event_Time"].tolist() == [12, 55, 92]
    assert summ["Event_Half"].tolist() == [1, 2, 2]
    assert summ["Event_Type"].tolist()[1] == "Penalty"
    assert summ["Score_Progression"].tolist() == ["1:0", "1:1", "2:1"]
