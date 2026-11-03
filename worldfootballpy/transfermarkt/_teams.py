"""Funciones de Transfermarkt a nivel de equipo y cuerpo técnico.

Traducción de tm_squad_stats.R, tm_staff_job_history.R,
tm_team_staff_history.R y tm_team_transfers.R.
"""

from __future__ import annotations

import re
from datetime import date

import numpy as np
import pandas as pd

from .. import _http
from .._utils import (
    TM,
    as_list,
    convert_value_to_numeric,
    janitor_clean_name,
    progress,
    squish,
    tm_fix_dates,
    to_date,
)
from ._common import TM_STAFF_CSV, first_attr, first_text, frame, full_url, load, tbody_rows
from ._league import _RowsView


def _performance_table(team_url):
    """Datos de rendimiento de la plantilla (página ``leistungsdaten``)."""
    page = load(team_url.replace("startseite", "leistungsdaten"))
    rows = []
    for box in page.cssselect("#yw1"):
        tables = box.cssselect("table")
        if tables:
            for tb in tables[0].cssselect("tbody"):
                rows.extend(c for c in tb if isinstance(c.tag, str))
            break
    return page, _RowsView(rows)


def _num(vals, fn=lambda v: v):
    return [pd.to_numeric(fn(v), errors="coerce") for v in vals]


def tm_squad_stats(team_url):
    """Estadísticas de la plantilla en la temporada: convocatorias, partidos, goles y minutos."""
    frames = []
    for url in progress(as_list(team_url), "tm_squad_stats"):
        try:
            page, b = _performance_table(url)
        except Exception as e:
            print(f"Error en {url}: {e}")
            continue
        names = [n.text_content() for h in b.nodes(".hauptlink") for n in h.cssselect(".hide-for-small")]
        purls = [full_url(a.get("href")) for h in b.nodes(".hauptlink") for a in h.cssselect(".hide-for-small a")]
        df = frame({
            "team_name": first_text(page, ".data-header__headline-wrapper--oswald"),
            "league": first_text(page, ".data-header__club a"),
            "country": first_attr(page, ".vm", "title"),
            "player_name": names,
            "player_url": purls,
            "player_pos": b.texts(".inline-table tr + tr td"),
            "player_age": _num(b.texts(".posrela + .zentriert")),
            "nationality": b.attrs(".flaggenrahmen:nth-child(1)", "title"),
            "in_squad": _num(b.texts("td:nth-child(5)"), lambda v: v.replace("-", "0")),
            "appearances": _num(b.texts("td:nth-child(6)"), lambda v: re.sub(r"Not.*", "0", v)),
            "goals": _num(b.texts(".zentriert:nth-child(7)"), lambda v: v.replace("-", "0")),
            "minutes_played": _num(b.texts(".rechts"), lambda v: v.replace(".", "").replace("'", "").replace("-", "0")),
        }, n=len(names))
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def tm_staff_job_history(staff_urls):
    """Trayectoria de entrenadores/staff: clubes, cargo, fechas, partidos, victorias, PPM."""
    frames = []
    for url in progress(as_list(staff_urls), "tm_staff_job_history"):
        try:
            pg = load(url.replace("profil", "stationen") + "/plus/1")
            name = first_text(pg, "h1")
            current_club = first_text(pg, ".data-header__club a", squish_it=False)
            current_role = first_text(pg, ".data-header__label b")
            meta = {}
            for li in [li for d in pg.cssselect(".data-header__details") for li in d.cssselect(".data-header__items li")]:
                t = squish(li.text_content())
                k, _, v = t.partition(":")
                meta.setdefault(janitor_clean_name(k), v.strip() if _ else np.nan)
            if "date_of_birth_age" in meta:
                v = meta.pop("date_of_birth_age")
                meta["date_of_birth"] = v.split(" (")[0] if isinstance(v, str) else v
            rows = tbody_rows(pg)
            b = _RowsView(rows)
            clubs = b.texts(".no-border-links a")
            goals = b.texts("td:nth-child(11)")

            def inner(v):
                return squish(re.sub(r"\).*", "", re.sub(r".*\(", "", v)))

            positions = b.texts("td:nth-child(2)")
            positions = [p.replace(c, "") if isinstance(c, str) else p for p, c in zip(positions, clubs + [np.nan] * len(positions))]
            df = frame({
                "name": name, "current_club": current_club, "current_role": current_role,
                **{k: v for k, v in meta.items()},
                "position": positions,
                "club": clubs,
                "appointed": tm_fix_dates([inner(v) for v in b.texts(".no-border-links + .zentriert")]),
                "contract_expiry": tm_fix_dates([inner(v).replace("expected ", "") for v in b.texts("td:nth-child(4)")]),
                "days_in_charge": _num(b.texts("td:nth-child(5)"), lambda v: v.replace(" Days", "")),
                "matches": _num(b.texts("td:nth-child(6)")),
                "wins": _num(b.texts("td:nth-child(7)")),
                "draws": _num(b.texts("td:nth-child(8)")),
                "losses": _num(b.texts("td:nth-child(9)")),
                "players_used": _num(b.texts("td:nth-child(10)")),
                "avg_goals_for": _num(goals, lambda v: squish(re.sub(r":.*", "", v))),
                "avg_goals_against": _num(goals, lambda v: squish(re.sub(r".*:", "", v))),
                "ppm": _num(b.texts("td:nth-child(12)")),
            }, n=len(rows))
            df["staff_url"] = url
            frames.append(df)
        except Exception as e:
            print(f"Error en {url}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def tm_team_staff_history(team_urls, staff_role="Manager"):
    """Historial de entrenadores (u otro rol del staff) de equipos, con partidos y PPG."""
    types = _http.read_csv_url(TM_STAFF_CSV)
    mask = types["staff_type_text"].str.lower() == staff_role.lower()
    if not mask.any():
        raise ValueError("Check that staff role exists...")
    idx = types.loc[mask, "staff_type_idx"].iloc[0]
    frames = []
    for team_url in progress(as_list(team_urls), "tm_team_staff_history"):
        try:
            url = re.sub(r"saison_id.*", "", team_url.replace("startseite", "mitarbeiterhistorie"))
            url = f"{url}personalie_id/{idx}/plus/1"
            pg = load(url)
            rows = tbody_rows(pg)
            recs = []
            for tr in rows:
                def first(css, attr=None):
                    n = tr.cssselect(css)
                    if not n:
                        return np.nan
                    return n[0].get(attr) if attr else n[0].text_content()

                hl = tr.cssselect(".hauptlink")
                link = hl[0].cssselect("a") if hl else []
                nats = [f.get("title") for f in tr.cssselect(".zentriert .flaggenrahmen")]
                recs.append({
                    "staff_name": link[0].text_content() if link else np.nan,
                    "staff_url": full_url(link[0].get("href")) if link else np.nan,
                    "staff_dob": first(".inline-table tr + tr td"),
                    "staff_nationality": nats[0] if nats else np.nan,
                    "staff_nationality_secondary": nats[1] if len(nats) > 1 else np.nan,
                    "appointed": tm_fix_dates(first("td:nth-child(3)")),
                    "end_date": tm_fix_dates(first("td:nth-child(4)")),
                    "days_in_post": first("td.rechts"),
                    "matches": pd.to_numeric(first(".rechts + td"), errors="coerce"),
                    "wins": pd.to_numeric(first("td:nth-child(7)"), errors="coerce"),
                    "draws": pd.to_numeric(first("td:nth-child(8)"), errors="coerce"),
                    "losses": pd.to_numeric(first("td:nth-child(9)"), errors="coerce"),
                    "ppg": pd.to_numeric(first("td:nth-child(10)"), errors="coerce"),
                })
            df = pd.DataFrame(recs)
            if len(df) == 0:
                continue
            for c in ("matches", "wins", "draws", "losses", "ppg"):
                df[c] = df[c].fillna(0)
            df["appointed"] = to_date(df["appointed"])
            df["end_date"] = to_date(df["end_date"])
            today = pd.Timestamp(date.today())
            df["days_in_post"] = np.where(
                df["end_date"].isna(), (today - df["appointed"]).dt.days, (df["end_date"] - df["appointed"]).dt.days
            ).astype(float)
            df.insert(0, "staff_role", staff_role)
            df.insert(0, "country", first_attr(pg, ".data-header__content img", "title"))
            df.insert(0, "league", first_text(pg, ".data-header__club a"))
            df.insert(0, "team_name", first_text(pg, "h1"))
            frames.append(df)
        except Exception as e:
            print(f"Error en {team_url}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def tm_team_transfers(team_url, transfer_window="all"):
    """Llegadas y salidas de equipos en una temporada (``"all"``, ``"summer"`` o ``"winter"``)."""
    tw = transfer_window.lower()
    if tw not in ("all", "summer", "winter"):
        raise ValueError("check transfer window is either 'all', 'summer' or 'winter'")
    windows = {"all": ["s", "w"], "summer": ["s"], "winter": ["w"]}[tw]
    frames = []
    for each_url in progress(as_list(team_url), "tm_team_transfers"):
        xfers_url = each_url.replace("startseite", "transfers")
        page = load(xfers_url)
        team_name = first_text(page, "h1")
        league = first_text(page, ".data-header__club a")
        country = first_attr(page, ".data-header__content img", "title")
        season = re.sub(r".*saison_id/", "", xfers_url)
        boxes = page.cssselect(".box")
        win_boxes = [bx for bx in boxes if any("Transfers " in squish(h.text_content()) for h in bx.cssselect("h2"))]
        actions = [ch.get("action") for bx in win_boxes for c in bx.cssselect(".content") for ch in c
                   if isinstance(ch.tag, str) and ch.get("action")]
        recs = []
        for w in windows:
            for action in actions[:1]:
                wpage = load(f"{TM}{action}?saison_id={season}&pos=&detailpos=&w_s={w}")
                for bx in wpage.cssselect(".box"):
                    h2 = bx.cssselect("h2")
                    title = squish(h2[0].text_content()) if h2 else ""
                    if title not in ("Arrivals", "Departures"):
                        continue
                    tables = bx.cssselect(".responsive-table")
                    if not tables or not tables[0].cssselect("tbody"):
                        continue
                    for tr in [c for c in tables[0].cssselect("tbody")[0] if isinstance(c.tag, str)]:
                        recs.append(_transfer_row(tr, title, w))
        df = pd.DataFrame(recs)
        if len(df) == 0:
            continue
        df["window"] = df["window"].map({"s": "Summer", "w": "Winter"}).fillna("Unknown")
        df.insert(0, "season", season)
        df.insert(0, "country", country)
        df.insert(0, "league", league)
        df.insert(0, "team_name", team_name)
        fee = [notes if isinstance(dup, str) and "Loan fee:" in dup else f
               for f, dup, notes in zip(df["transfer_fee"], df["transfer_fee_dup"], df["transfer_fee_notes1"])]
        df["transfer_fee"] = [convert_value_to_numeric(v) for v in fee]
        df["transfer_fee_dup"] = [
            (d.replace("End of loan", "End of loan ") if isinstance(d, str) else d) if pd.isna(f) else np.nan
            for f, d in zip(df["transfer_fee"], df["transfer_fee_dup"])
        ]
        df = df.rename(columns={"transfer_fee_dup": "transfer_notes"}).drop(columns=["transfer_fee_notes1"])

        _, b = _performance_table(each_url)
        names = [n.text_content() for h in b.nodes(".hauptlink") for n in h.cssselect(".hide-for-small")]
        perf = frame({
            "player_name": names,
            "in_squad": _num(b.texts("td:nth-child(5)"), lambda v: v.replace("-", "0")),
            "appearances": _num(b.texts("td:nth-child(6)"), lambda v: re.sub(r"Not.*", "0", v)),
            "goals": _num(b.texts(".zentriert:nth-child(7)"), lambda v: v.replace("-", "0")),
            "minutes_played": _num(b.texts(".rechts"), lambda v: v.replace(".", "").replace("'", "").replace("-", "0")),
        }, n=len(names)).drop_duplicates(subset=["player_name"])
        df = df.merge(perf, on="player_name", how="left")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out[out["player_name"].notna()].reset_index(drop=True)


def _transfer_row(tr, title, window):
    def first_text_(css):
        n = tr.cssselect(css)
        if not n:
            return np.nan
        t = n[0].text_content()
        return t if t != "" else np.nan

    hl = tr.cssselect(".hauptlink")
    link = hl[0].cssselect("a") if hl else []
    inline_links = [a for t in tr.cssselect(".inline-table") for a in t.cssselect("a")]
    nats = [f.get("title") for f in tr.cssselect(".zentriert .flaggenrahmen")]
    countries = [f.get("alt") for f in tr.cssselect(".inline-table .flaggenrahmen")]
    fee = first_text_(".rechts a")
    notes = [i.text_content() for i in tr.cssselect(".rechts.hauptlink a i")]
    return {
        "transfer_type": title,
        "player_name": link[0].text_content() if link else np.nan,
        "player_url": full_url(link[0].get("href")) if link else np.nan,
        "player_position": first_text_("td:nth-child(2) tr + tr td"),
        "player_age": first_text_("td.zentriert:nth-child(3)"),
        "player_nationality": nats[0] if nats else np.nan,
        "club_2": inline_links[2].text_content() if len(inline_links) > 2 else np.nan,
        "league_2": first_text_(".flaggenrahmen + a"),
        "country_2": countries[0] if countries else np.nan,
        "transfer_fee": fee,
        "is_loan": bool(re.search("loan", fee, flags=re.I)) if isinstance(fee, str) else False,
        "transfer_fee_dup": fee,
        "transfer_fee_notes1": notes[0] if notes else np.nan,
        "window": window,
    }


__all__ = ["tm_squad_stats", "tm_staff_job_history", "tm_team_staff_history", "tm_team_transfers"]
