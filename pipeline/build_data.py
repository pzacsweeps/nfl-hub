"""Rebuild data.json from pipeline/base.json (the original Excel tracker's data) plus every
pipeline/weeks/supp_wk*.json (weeks added from box scores). Usage: python3 build_data.py out.json"""
import sys, json, os
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1]
BASE = json.load(open(os.path.join(HERE, "base.json")))
teams = {t["name"]: t for t in BASE["teams"]}
order = BASE["order"]

# ---------- supplemental weeks (box scores added after the Excel) ----------
import glob as _glob, os as _os
SUPP = [json.load(open(f)) for f in sorted(_glob.glob(_os.path.join(HERE, "weeks", "supp_wk*.json")), key=lambda f: int(f.split("wk")[-1].split(".")[0]))]
for _s in SUPP:
    for _r in _s["team_rows"]:
        for _g in teams[_r["Team"]]["schedule"]:
            if _g["wk"] == _r["Week"]:
                _g["res"] = f'{_r["Result"]} {_r["Pts"]}-{_r["Pts Allowed"]}'

# ---------- Team Log -> per-team aggregates & ranks ----------
C = {k: 0 for k in ["Week", "Team", "Opponent", "Venue", "Pts", "Pass Yds", "Rush Yds", "Total Yds",
                         "Turnovers", "Result", "Pts Allowed", "Pass Yds Allowed", "Rush Yds Allowed",
                         "Total Yds Allowed", "Takeaways", "1H Pts", "2H Pts", "TDs", "FG Made", "FG Att",
                         "XP Made", "XP Att", "Plays", "1st Downs", "3rd Conv", "3rd Att", "4th Conv", "4th Att",
                         "Sacks Taken", "Penalties", "Pen Yds", "TOP (min)", "1H Pts Allowed", "2H Pts Allowed",
                         "TDs Allowed", "FG Made Allowed", "FG Att Allowed", "Plays Allowed",
                         "1st Downs Allowed", "Opp 3rd Conv", "Opp 3rd Att", "Opp 4th Conv", "Opp 4th Att",
                         "Sacks Made"]}

H = list(C)  # keys in order; rows are tuples indexed by C
C = {k: i for i, k in enumerate(H)}
tl = [tuple(r[k] for k in H) for r in BASE["team_rows"]]
_have = {(r[C["Week"]], r[C["Team"]]) for r in tl}
for _s in SUPP:
    for _r in _s["team_rows"]:
        if (_r["Week"], _r["Team"]) in _have:
            continue
        _row = [None] * len(H)
        for _k, _i in C.items():
            _row[_i] = _r[_k]
        tl.append(tuple(_row))

agg = defaultdict(lambda: defaultdict(float))
rec = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "hW": 0, "hL": 0, "hT": 0, "aW": 0, "aL": 0, "aT": 0})
games = []
for r in tl:
    t = r[C["Team"]]
    a = agg[t]
    a["gp"] += 1
    for k in C:
        if k in ("Week", "Team", "Opponent", "Venue", "Result"):
            continue
        a[k] += r[C[k]] or 0
    res = r[C["Result"]] or ("W" if r[C["Pts"]] > r[C["Pts Allowed"]] else "L" if r[C["Pts"]] < r[C["Pts Allowed"]] else "T")
    rec[t][res] += 1
    rec[t][("h" if r[C["Venue"]] == "Home" else "a") + res] += 1
    games.append({"wk": r[0], "team": t, "opp": r[C["Opponent"]], "venue": r[C["Venue"]],
                  "pts": r[C["Pts"]], "pa": r[C["Pts Allowed"]]})


def rs(w, l, t):
    return f"{w}-{l}" + (f"-{t}" if t else "")


def div(a, b):
    return a / b if b else None


# stat definitions: (key, label, off fn, def fn, offHigherBetter, defLowerBetter, fmt)
def pg(k):
    return lambda a: a[k] / a["gp"]


STATS = [
    ("pts", "Points", pg("Pts"), pg("Pts Allowed"), True, True, "1"),
    ("pass", "Pass Yds", pg("Pass Yds"), pg("Pass Yds Allowed"), True, True, "1"),
    ("rush", "Rush Yds", pg("Rush Yds"), pg("Rush Yds Allowed"), True, True, "1"),
    ("tot", "Total Yds", pg("Total Yds"), pg("Total Yds Allowed"), True, True, "1"),
    ("h1", "1st Half Pts", pg("1H Pts"), pg("1H Pts Allowed"), True, True, "1"),
    ("h2", "2nd Half Pts", pg("2H Pts"), pg("2H Pts Allowed"), True, True, "1"),
    ("td", "Touchdowns", pg("TDs"), pg("TDs Allowed"), True, True, "2"),
    ("fgm", "FG Made", pg("FG Made"), pg("FG Made Allowed"), True, True, "2"),
    ("fga", "FG Attempts", pg("FG Att"), pg("FG Att Allowed"), True, True, "2"),
    ("ypp", "Yards / Play", lambda a: div(a["Total Yds"], a["Plays"]), lambda a: div(a["Total Yds Allowed"], a["Plays Allowed"]), True, True, "2"),
    ("fd", "1st Downs", pg("1st Downs"), pg("1st Downs Allowed"), True, True, "1"),
    ("third", "3rd Down %", lambda a: div(a["3rd Conv"], a["3rd Att"]), lambda a: div(a["Opp 3rd Conv"], a["Opp 3rd Att"]), True, True, "%"),
    ("fourth", "4th Down %", lambda a: div(a["4th Conv"], a["4th Att"]), lambda a: div(a["Opp 4th Conv"], a["Opp 4th Att"]), True, True, "%"),
    ("plays", "Plays", pg("Plays"), pg("Plays Allowed"), True, True, "1"),
    ("sacks", "Sacks (taken vs made)", pg("Sacks Taken"), pg("Sacks Made"), False, False, "2"),
    ("to", "Turnovers vs Takeaways", pg("Turnovers"), pg("Takeaways"), False, False, "2"),
]


def rank(values, higher_better):
    """Excel RANK.EQ style: ties share the best rank. values: {team: v}"""
    out = {}
    vals = [v for v in values.values() if v is not None]
    for t, v in values.items():
        if v is None:
            out[t] = None
            continue
        better = sum(1 for x in vals if (x > v + 1e-9 if higher_better else x < v - 1e-9))
        out[t] = better + 1
    return out


team_stats = {t: {"off": {}, "def": {}, "offRank": {}, "defRank": {}} for t in order}
for key, label, fo, fd, off_hi, def_lo, fmt in STATS:
    ov = {t: (fo(agg[t]) if agg[t]["gp"] else None) for t in order}
    dv = {t: (fd(agg[t]) if agg[t]["gp"] else None) for t in order}
    orank = rank(ov, off_hi)
    drank = rank(dv, not def_lo)
    for t in order:
        ts = team_stats[t]
        ts["off"][key], ts["def"][key] = ov[t], dv[t]
        ts["offRank"][key], ts["defRank"][key] = orank[t], drank[t]

summary = {}
for t in order:
    a, r = agg[t], rec[t]
    gp = a["gp"]
    summary[t] = {
        "record": rs(r["W"], r["L"], r["T"]), "gp": int(gp),
        "ppg": div(a["Pts"], gp), "papg": div(a["Pts Allowed"], gp),
        "diff": div(a["Pts"] - a["Pts Allowed"], gp),
        "tom": div(a["Takeaways"] - a["Turnovers"], gp),
        "fgp": div(a["FG Made"], a["FG Att"]), "xpp": div(a["XP Made"], a["XP Att"]),
        "pen": div(a["Penalties"], gp), "penyds": div(a["Pen Yds"], gp), "top": div(a["TOP (min)"], gp),
        "home": rs(r["hW"], r["hL"], r["hT"]), "away": rs(r["aW"], r["aL"], r["aT"]),
    }

# ---------- Player Log ----------
PALIAS = {k: v for k, v in json.load(open(os.path.join(HERE, "player_aliases.json"))).items() if not k.startswith("_")}
for _r in BASE["player_rows"] + [r for _s in SUPP for r in _s["player_rows"]]:
    _r["name"] = PALIAS.get(_r["name"], _r["name"])
players = defaultdict(lambda: {"games": []})
for _r in BASE["player_rows"]:
    p = players[(_r["name"], _r["team"])]
    p["name"], p["pos"], p["team"] = _r["name"], _r["pos"], _r["team"]
    p["games"].append({k: _r[k] for k in ("wk", "opp", "cmp", "patt", "pyds", "ptd", "int", "ratt", "ryds", "rtd", "tgt", "rec", "recyds", "rectd")})

for _s in SUPP:
    for _r in _s["player_rows"]:
        p = players[(_r["name"], _r["team"])]
        if any(g["wk"] == _r["wk"] for g in p["games"]):
            continue
        p["name"], p["pos"], p["team"] = _r["name"], _r["pos"], _r["team"]
        p["games"].append({k: _r[k] for k in ("wk", "opp", "cmp", "patt", "pyds", "ptd", "int", "ratt", "ryds", "rtd", "tgt", "rec", "recyds", "rectd")})

# ---------- one card per player: merge a traded player's stints (same name and position, no week played twice) ----------
for g_ in players.values():
    for x in g_["games"]:
        x["tm"] = g_["team"]
_by = defaultdict(list)
for k, p in players.items():
    _by[(p["name"], p["pos"])].append(k)
TRADES = []
for (nm, pos), keys in _by.items():
    if len(keys) < 2:
        continue
    wks = [g["wk"] for k in keys for g in players[k]["games"]]
    if len(wks) != len(set(wks)):
        print("same name, overlapping weeks (kept apart):", nm, [k[1] for k in keys])
        continue
    games_ = sorted((g for k in keys for g in players[k]["games"]), key=lambda g: g["wk"])
    stints = []
    for g in games_:
        if stints and stints[-1]["team"] == g["tm"]:
            stints[-1]["to"] = g["wk"]
        else:
            stints.append({"team": g["tm"], "from": g["wk"], "to": g["wk"]})
    cur = stints[-1]["team"]
    for k in keys:
        del players[k]
    players[(nm, cur)] = {"name": nm, "pos": pos, "team": cur, "games": games_, "stints": stints}
    TRADES.append(f"{nm}: " + " -> ".join(f"{s_['team']} (wk {s_['from']}-{s_['to']})" for s_ in stints))
for p in players.values():
    if "stints" not in p:
        for g in p["games"]:
            g.pop("tm", None)
print("merged across teams:", *TRADES, sep="\n  ")

# ---------- Defence vs Position (computed from logs, verified vs sheet) ----------
allowed = defaultdict(lambda: defaultdict(float))
for p in players.values():
    for g in p["games"]:
        d = allowed[g["opp"]]
        pos = p["pos"]
        if pos == "QB":
            d["qbpy"] += g["pyds"]; d["qbptd"] += g["ptd"]; d["qbry"] += g["ryds"]
        elif pos == "RB":
            d["rbry"] += g["ryds"]; d["rbrecy"] += g["recyds"]
        elif pos == "WR":
            d["wrry"] += g["recyds"]; d["wrrec"] += g["rec"]
        elif pos == "TE":
            d["tery"] += g["recyds"]; d["terec"] += g["rec"]

DVP = [  # key, label, group
    ("pts", "Pts", "team"), ("pass", "Pass Yds", "team"), ("rush", "Rush Yds", "team"), ("tot", "Total Yds", "team"),
    ("qbpy", "QB Pass Yds", "QB"), ("qbptd", "QB Pass TD", "QB"), ("qbry", "QB Rush Yds", "QB"),
    ("rbry", "RB Rush Yds", "RB"), ("rbrecy", "RB Rec Yds", "RB"),
    ("wrry", "WR Rec Yds", "WR"), ("wrrec", "WR Rec", "WR"),
    ("tery", "TE Rec Yds", "TE"), ("terec", "TE Rec", "TE"),
    ("take", "Takeaways", "team"),
]
dvp = {t: {"gp": int(agg[t]["gp"]), "val": {}, "rank": {}} for t in order}
src_map = {"pts": "Pts Allowed", "pass": "Pass Yds Allowed", "rush": "Rush Yds Allowed",
           "tot": "Total Yds Allowed", "take": "Takeaways"}
for key, label, grp in DVP:
    vals = {}
    for t in order:
        gp = agg[t]["gp"]
        if not gp:
            vals[t] = None
        elif key in src_map:
            vals[t] = agg[t][src_map[key]] / gp
        else:
            vals[t] = allowed[t][key] / gp
    rk = rank(vals, key == "take")  # 1 = toughest (allows least); takeaways 1 = most
    for t in order:
        dvp[t]["val"][key], dvp[t]["rank"][key] = vals[t], rk[t]

# player list
plist = []
for p in players.values():
    p["games"].sort(key=lambda g: g["wk"])
    plist.append(p)
plist.sort(key=lambda p: (p["team"], ["QB", "RB", "WR", "TE"].index(p["pos"]), p["name"]))

played_weeks = sorted({g["wk"] for g in games})
data = {
    "teams": [teams[t] for t in order],
    "summary": summary,
    "teamStats": team_stats,
    "stats": [{"key": s[0], "label": s[1], "fmt": s[6], "offHi": s[4], "defLo": s[5]} for s in STATS],
    "dvpCols": [{"key": k, "label": l, "grp": g} for k, l, g in DVP],
    "dvp": dvp,
    "players": plist,
    "lastWeek": max(played_weeks) if played_weeks else 0,
    "source": "NFL_2026.xlsx + weekly box scores",
}
with open(out, "w") as f:
    json.dump(data, f, separators=(",", ":"))
print("teams", len(order), "players", len(plist), "last week", data["lastWeek"])
