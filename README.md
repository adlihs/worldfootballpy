# worldfootballpy

Port a Python del paquete de R [worldfootballR](https://github.com/JaseZiv/worldfootballR) (v0.6.8) de Jason Zivkovic. Extrae datos de fútbol de **FBref**, **Transfermarkt** y **Understat** y los devuelve como `pandas.DataFrame`, con los mismos nombres de funciones y de columnas que la versión de R.

```python
import worldfootballpy as wf

# Resultados de la Premier League 2023-24 (FBref)
resultados = wf.fb_match_results(country="ENG", gender="M", season_end_year=2024, tier="1st")

# Datos ya preparados, sin visitar FBref (rápido)
big5 = wf.load_fb_big5_advanced_season_stats(season_end_year=2025, stat_type="shooting", team_or_player="player")

# Valores de mercado de una plantilla (Transfermarkt)
arsenal = wf.tm_each_team_player_market_val(
    "https://www.transfermarkt.com/fc-arsenal/startseite/verein/11/saison_id/2025"
)

# Resultados con xG y pronósticos (Understat)
epl = wf.understat_league_match_results(league="EPL", season_start_year=2024)
```

## Instalación

```bash
pip install git+https://github.com/adlihs/worldfootballpy.git
# opcional: barra de progreso
pip install tqdm
```

Requiere Python 3.9+ y depende de `pandas`, `requests`, `lxml`, `cssselect` y `rdata` (para leer los archivos `.rds` de worldfootballR_data).

## Qué incluye

Las 74 funciones públicas de worldfootballR 0.6.8 están disponibles. Si ya conoces el paquete de R, el código se traduce casi línea por línea:

| R | Python |
|---|---|
| `fb_match_results(country = "ENG", gender = "M", season_end_year = 2024)` | `wf.fb_match_results(country="ENG", gender="M", season_end_year=2024)` |
| `season_end_year = c(2023, 2024)` | `season_end_year=[2023, 2024]` |
| `league_url = NA` | `league_url=None` (o simplemente no pasarlo) |
| `options(worldfootballR.agent = "...")` | `wf.set_user_agent("...")` |

### FBref

- **Partidos:** `fb_match_urls`, `fb_match_results`, `fb_match_report`, `fb_match_summary`, `fb_match_lineups`, `fb_match_shooting`, `fb_advanced_match_stats`, `fb_team_match_stats`
- **Temporadas:** `fb_season_team_stats`, `fb_big5_advanced_season_stats`, `fb_league_stats`, `fb_team_player_stats`, `fb_player_season_stats`
- **Equipos:** `fb_teams_urls`, `fb_team_match_results`, `fb_team_match_log_stats`, `fb_team_goal_logs`, `fb_squad_wages`
- **Jugadores:** `fb_player_urls`, `fb_player_info`, `fb_player_match_logs`, `fb_player_goal_logs`, `fb_player_scouting_report`
- **Ligas:** `fb_league_urls`
- **Datos precargados (no visitan FBref):** `load_match_results`, `load_match_comp_results`, `load_fb_big5_advanced_season_stats`, `load_fb_match_shooting`, `load_fb_match_summary`, `load_fb_advanced_match_stats`, `player_dictionary_mapping`

### Transfermarkt

- **Ligas:** `tm_league_team_urls`, `tm_matchday_table`, `tm_team_transfer_balances`, `tm_expiring_contracts`, `tm_league_debutants`, `tm_league_injuries`, `tm_get_suspensions`, `tm_get_risk_of_suspension`
- **Equipos:** `tm_team_player_urls`, `tm_squad_stats`, `tm_team_transfers`, `tm_each_team_player_market_val`, `tm_player_market_values`
- **Jugadores:** `tm_player_bio`, `tm_player_transfer_history`, `tm_player_injury_history`, `tm_get_player_absence`
- **Cuerpo técnico:** `tm_team_staff_urls`, `tm_team_staff_history`, `tm_staff_job_history`

### Understat

`understat_league_match_results`, `understat_league_season_shots`, `understat_team_season_shots`, `understat_match_shots`, `understat_match_players`, `understat_match_stats`, `understat_player_shots`, `understat_team_players_stats`, `understat_team_stats_breakdown`, `understat_team_meta`, `understat_available_teams`, `load_understat_league_shots`.

Los nombres antiguos que R marca como obsoletos (`get_match_results`, `get_match_lineups`, `get_player_market_values`, etc.) también existen y avisan con un `DeprecationWarning`.

## Diferencias con la versión de R

- **FotMob no está incluido.** El autor de worldfootballR eliminó esas funciones porque los términos de servicio de FotMob prohíben el acceso automatizado.
- **`fb_league_stats(team_or_player="player")` no necesita Chrome.** En R depende de `read_html_live`; aquí la tabla se lee de los comentarios HTML donde FBref la esconde.
- **Fechas:** las columnas que R convierte con `lubridate::ymd` son `datetime64` de pandas. Algunas fechas de Transfermarkt se quedan como texto `"YYYY-MM-DD"`, igual que en R.
- **Valores ausentes:** `NA` de R se representa como `NaN`/`None`.

## Uso responsable

- **FBref** limita el acceso a unas 10 peticiones por minuto y puede bloquear tu IP si te pasas. Por eso las funciones esperan `time_pause=3` segundos entre páginas. No bajes ese valor.
- Para análisis grandes usa primero las funciones `load_*`: descargan datos ya preparados desde GitHub sin tocar los sitios.
- **Transfermarkt:** usa siempre las URLs en inglés (`www.transfermarkt.com`), porque los selectores dependen de las cabeceras en inglés.
- Cita la fuente de los datos (FBref/Opta, Transfermarkt, Understat) cuando publiques análisis.

## Estado

Versión 0.1.0. Las funciones se tradujeron del código fuente de worldfootballR y se probaron con HTML de ejemplo (`tests/`). Las funciones `load_*` se probaron contra los datos reales de GitHub. **El scraping en vivo de FBref, Transfermarkt y Understat todavía no se ha probado contra los sitios reales.** Esos sitios cambian su HTML con frecuencia; si una función falla, abre un *issue* con la URL que usaste.

```bash
pip install -e ".[dev]"
pytest
```

## Créditos y licencia

Basado en [worldfootballR](https://github.com/JaseZiv/worldfootballR) de Jason Zivkovic y colaboradores, y en los datos de [worldfootballR_data](https://github.com/JaseZiv/worldfootballR_data). Distribuido bajo GPL-3.0, la misma licencia del paquete original.
