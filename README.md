# NFL 2026 Hub

Schedule and results, injury report, matchup analyser with a game prop check, and player cards (every game vs the opponent's full defence-vs-position profile) with a player prop check.

Live site: https://pzacsweeps.github.io/nfl-hub/

## Automatic updates (GitHub Actions)
All times UK.
- **Stats** (`stats.yml`): Tuesday morning. If every game of the next week is final, the ESPN box scores are pulled (`pipeline/fetch_week.py`), the week is added and the site is rebuilt. Wednesday morning is a retry.
- **Injuries** (`injuries.yml`): Thursday 22:00, Sunday 09:00 and Sunday 30 minutes before the first kickoff. Official NFL.com report (practice participation and game statuses) plus the CBS Sports injury page (IR / PUP / NFI lists, late downgrades, return weeks), merged by `pipeline/fetch_injuries.py`.

Run either by hand: Actions tab → pick the workflow → **Run workflow** (works from the GitHub mobile app). `Weekly stats update` takes an optional week number to reload one week.

## Files
- `index.html` — the site (built, do not edit by hand)
- `pipeline/app_template.html` — the app page; data is injected at build time
- `pipeline/base.json` — the original NFL_2026 tracker data (weeks 1-6, schedule, depth charts)
- `pipeline/weeks/supp_wkN.json` — each week added after that
- `pipeline/injuries.json`, `pipeline/meta.json` — current injury report and update stamps
- `pipeline/build_site.py` — rebuilds `index.html`
