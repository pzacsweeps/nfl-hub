"""Rebuild the site: data from base.json + weeks/, injuries.json and meta.json, injected into app_template.html.
Writes ../index.html (GitHub Pages) and nfl-hub.html (the same page without the document skeleton, for the Claude artifact).
    python3 pipeline/build_site.py"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
subprocess.run([sys.executable, os.path.join(HERE, "build_data.py"), os.path.join(HERE, "data.json")], check=True)
dj = json.load(open(os.path.join(HERE, "data.json")))
dj.update(json.load(open(os.path.join(HERE, "meta.json"))))
inj = json.load(open(os.path.join(HERE, "injuries.json")))
for t in dj["teams"]:
    if t["name"] in inj:
        t["injTitle"] = inj[t["name"]]["title"]
        t["injuries"] = inj[t["name"]]["injuries"]
body = open(os.path.join(HERE, "app_template.html"), encoding="utf-8").read().replace("/*__DATA__*/null", json.dumps(dj, separators=(",", ":")))
open(os.path.join(HERE, "nfl-hub.html"), "w", encoding="utf-8").write(body)
head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="NFL 2026 schedule and results, injury report, matchup analyser, game and player prop checks, and player cards vs full opponent defence ranks. By PZAC Sweeps.">
<meta property="og:title" content="NFL 2026 Hub">
<meta property="og:description" content="Schedule, injuries, matchups, prop checks and player cards vs defence-vs-position ranks. By @PZACSweeps.">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>
"""
i = body.index("</style>") + len("</style>")
open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(head + body[:i] + "\n</head>\n<body>\n" + body[i:] + "\n</body>\n</html>\n")
print("built: last week", dj["lastWeek"], "| injuries", dj.get("injUpdatedShort"))
