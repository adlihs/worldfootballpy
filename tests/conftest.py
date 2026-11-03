import pandas as pd
import pytest

from worldfootballpy import _http


@pytest.fixture
def fake_web(monkeypatch):
    """Sustituye la red por un diccionario {url: html} y CSVs en memoria."""
    pages = {}
    csvs = {}

    def load_page(url, **kwargs):
        if url not in pages:
            raise KeyError(f"URL no simulada: {url}")
        return _http.parse_html(pages[url])

    def read_csv_url(url):
        return csvs[url].copy()

    monkeypatch.setattr(_http, "load_page", load_page)
    monkeypatch.setattr(_http, "read_csv_url", read_csv_url)
    monkeypatch.setattr(_http, "sleep", lambda s: None)
    return pages, csvs


def competitions_row(**kw):
    base = {
        "competition_type": "Domestic Leagues - 1st Tier",
        "competition_name": "Premier League",
        "country": "ENG",
        "gender": "M",
        "governing_body": "UEFA",
        "first_season": "1888-1889",
        "last_season": "2024-2025",
        "tier": "1st",
        "comp_url": "https://fbref.com/en/comps/9/history/Premier-League-Seasons",
        "seasons": "2023-2024",
        "season_end_year": 2024,
        "seasons_urls": "https://fbref.com/en/comps/9/2023-2024/2023-2024-Premier-League-Stats",
        "fixtures_url": "https://fbref.com/en/comps/9/2023-2024/schedule/2023-2024-Premier-League-Scores-and-Fixtures",
    }
    base.update(kw)
    return base


def competitions(*rows):
    return pd.DataFrame(list(rows))
