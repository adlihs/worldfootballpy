"""Pruebas de las utilidades internas (sin red)."""

import numpy as np
import pandas as pd

from worldfootballpy import _http
from worldfootballpy._table import html_table, make_names
from worldfootballpy._utils import (
    clean_match_advanced_stats_data,
    convert_value_to_numeric,
    janitor_clean_name,
    rename_fb_cols,
    tm_fix_dates,
)


def table(html):
    return _http.parse_html(html).xpath("//table")[0]


TWO_HEADER = """
<table>
<thead>
<tr class="over_header"><th colspan="2"></th><th colspan="2">Playing Time</th><th colspan="2">Per 90 Minutes</th></tr>
<tr><th>Squad</th><th># Pl</th><th>MP</th><th>90s</th><th>Gls</th><th>G+A-PK</th></tr>
</thead>
<tbody>
<tr><th>Arsenal</th><td>25</td><td>38</td><td>38.0</td><td>2.5</td><td>1,234</td></tr>
<tr><th>Chelsea</th><td>30</td><td>38</td><td>38.0</td><td>1.9</td><td>3</td></tr>
</tbody></table>
"""


def test_make_names_like_r():
    assert make_names(["Playing Time", "Playing Time", "", "# Pl", "1/3"]) == [
        "Playing.Time", "Playing.Time.1", "X", "X..Pl", "X1.3"]


def test_html_table_keeps_second_header_row_like_rvest():
    df = html_table(table(TWO_HEADER))
    assert list(df.columns) == ["Var.1", "Var.2", "Playing.Time", "Playing.Time.1",
                                "Per.90.Minutes", "Per.90.Minutes.1"]
    assert df.iloc[0].tolist() == ["Squad", "# Pl", "MP", "90s", "Gls", "G+A-PK"]
    assert len(df) == 3


def test_rename_fb_cols_matches_worldfootballr_names():
    df = rename_fb_cols(html_table(table(TWO_HEADER)))
    assert list(df.columns) == ["Squad", "Num_Players", "MP_Playing_Time", "Mins_Per_90_Playing_Time",
                                "Gls_Per_Minutes", "G+A_minus_PK_Per_Minutes"]
    assert df["Squad"].tolist() == ["Arsenal", "Chelsea"]


def test_clean_match_advanced_stats_numeric():
    html = """<table><thead>
    <tr><th colspan="3"></th><th colspan="2">Performance</th></tr>
    <tr><th>Player</th><th>#</th><th>Nation</th><th>Gls</th><th>Cmp%</th></tr></thead>
    <tbody><tr><th>Joel Campbell</th><td>12</td><td>cr CRC</td><td>1</td><td>85.5</td></tr></tbody></table>"""
    df = clean_match_advanced_stats_data(html_table(table(html)))
    assert list(df.columns) == ["Player", "Player_Num", "Nation", "Gls", "Cmp_percent"]
    assert df.loc[0, "Nation"] == "CRC"
    assert df.loc[0, "Gls"] == 1.0


def test_colspan_rowspan_expansion():
    html = """<table><tr><th>A</th><th>B</th></tr>
    <tr><td rowspan="2">x</td><td>1</td></tr><tr><td>2</td></tr></table>"""
    df = html_table(table(html))
    assert df["A"].tolist() == ["x", "x"]
    assert df["B"].tolist() == [1, 2]


def test_convert_value_to_numeric():
    assert convert_value_to_numeric("€12.50m") == 12_500_000
    assert convert_value_to_numeric("€500k") == 500_000
    assert convert_value_to_numeric("€800Th.") == 800_000
    assert convert_value_to_numeric("free transfer") == 0
    assert convert_value_to_numeric("Loan fee:€1.00m") == 1_000_000
    assert np.isnan(convert_value_to_numeric("-"))
    assert np.isnan(convert_value_to_numeric(None))


def test_tm_fix_dates():
    assert tm_fix_dates("Jun 30, 2026") == "2026-06-30"
    assert tm_fix_dates("30.08.2029") == "2029-08-30"
    assert tm_fix_dates("2029.08.30") == "2029-08-30"
    assert pd.isna(tm_fix_dates("-"))
    assert tm_fix_dates(["Jan 1, 2020", None])[0] == "2020-01-01"


def test_janitor_clean_name():
    assert janitor_clean_name("FIFA Women's World Cup") == "fifa_womens_world_cup"
    assert janitor_clean_name("Date of birth/Age") == "date_of_birth_age"
    assert janitor_clean_name("Copa América Femenina") == "copa_america_femenina"
