"""Pull one week's box scores from ESPN's public API and write pipeline/weeks/supp_wk<N>.json
(the same rows the Excel tracker keeps: one Team Log row per team, one Player Log row per QB/RB/WR/TE).

    python3 pipeline/fetch_week.py 10              -> writes weeks/supp_wk10.json (only if every game is final)
    python3 pipeline/fetch_week.py 9 --check       -> compares ESPN with the saved weeks/supp_wk9.json, writes nothing
    python3 pipeline/fetch_week.py --status        -> prints the latest complete week and whether it is saved
"""
import json, os, re, sys, time, urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SEASON = int(os.environ.get("NFL_SEASON", "2026"))
SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w}&dates={y}"
SUM = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={e}"
ATH = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{a}"
NAMES = os.path.join(HERE, "espn_players.json")   # ESPN athlete id -> {name, pos} (log name and position)
ALIAS = {"Bam Knight": "Zonovan Knight", "Cam Ward": "Cameron Ward", "Woody Marks": "Jo'quavious Marks",
         "Hollywood Brown": "Marquise Brown", "Drew Ogletree": "Andrew Ogletree", "Bucky Irving": "Mar'Keise Irving",
         "Matt Hibner": "Matthew Hibner", "Reggie Virgil": "Reginald Virgil"}
POSMAP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE"}


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (nfl-hub data update)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def norm(n):
    n = n.lower().replace(".", "").replace("'", "").replace("’", "")
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def week_events(w):
    sb = get(SB.format(w=w, y=SEASON))
    return [{"id": e["id"], "name": e["shortName"], "date": e["date"],
             "final": e["status"]["type"].get("completed", False)} for e in sb.get("events", [])]


def known_players():
    """(team, normalised name) -> (log name, pos), from the current data."""
    base = json.load(open(os.path.join(HERE, "base.json")))
    rows = list(base["player_rows"])
    for f in os.listdir(os.path.join(HERE, "weeks")):
        if f.startswith("supp_wk"):
            rows += json.load(open(os.path.join(HERE, "weeks", f)))["player_rows"]
    k = {}
    for r in rows:
        k[(r["team"], norm(r["name"]))] = (r["name"], r["pos"])
    return k


def parse_game(s, week, sched, known, ids, problems):
    comp = s["header"]["competitions"][0]
    side = {}
    for c in comp["competitors"]:
        nm = c["team"]["displayName"]
        q = [int(float(l.get("displayValue", l.get("value", 0)) or 0)) for l in c.get("linescores", [])]
        q = (q + [0, 0, 0, 0])[:4] + [sum(q[4:])]
        side[nm] = {"ha": c["homeAway"], "q": q, "pts": int(c["score"])}
    teams = list(side)
    st = {}
    for t in s["boxscore"]["teams"]:
        d = {}
        for x in t["statistics"]:
            d.setdefault(x["name"], x["displayValue"])
        st[t["team"]["displayName"]] = d
    players = defaultdict(lambda: defaultdict(int))
    kick = defaultdict(lambda: [0, 0, 0, 0])
    for blk in s["boxscore"].get("players", []):
        tm = blk["team"]["displayName"]
        for cat in blk["statistics"]:
            lab = cat.get("labels", [])
            for a in cat.get("athletes", []):
                v = dict(zip(lab, a.get("stats", [])))
                aid, nm = a["athlete"]["id"], a["athlete"]["displayName"]
                num = lambda k: int(float(v.get(k, "0") or 0)) if re.match(r"^-?[\d.]+$", str(v.get(k, "0"))) else 0
                if cat["name"] == "kicking":
                    fg = v.get("FG", "0/0").split("/"); xp = v.get("XP", "0/0").split("/")
                    k = kick[tm]; k[0] += int(fg[0]); k[1] += int(fg[1]); k[2] += int(xp[0]); k[3] += int(xp[1])
                    continue
                r = players[(tm, aid, nm)]
                if cat["name"] == "passing":
                    ca = v.get("C/ATT", "0/0").split("/")
                    r["cmp"] += int(ca[0]); r["patt"] += int(ca[1]); r["pyds"] += num("YDS"); r["ptd"] += num("TD"); r["int"] += num("INT")
                elif cat["name"] == "rushing":
                    r["ratt"] += num("CAR"); r["ryds"] += num("YDS"); r["rtd"] += num("TD")
                elif cat["name"] == "receiving":
                    r["tgt"] += num("TGTS"); r["rec"] += num("REC"); r["recyds"] += num("YDS"); r["rectd"] += num("TD")
    team_rows, player_rows = [], []
    for t in teams:
        o = teams[1] if t == teams[0] else teams[0]
        T, O = st[t], st[o]
        g = sched[t]
        if g["opp"] != o:
            problems.append(f"{t}: schedule says week {week} opponent is {g['opp']}, ESPN says {o}")
        q, pts, opts = side[t]["q"], side[t]["pts"], side[o]["pts"]
        if sum(q) != pts:
            problems.append(f"{t}: quarters {q} != {pts}")
        fgm, fga, xpm, xpa = kick[t]
        third, fourth = T["thirdDownEff"].split("-"), T["fourthDownEff"].split("-")
        pen = T["totalPenaltiesYards"].split("-")
        sacks = int(T["sacksYardsLost"].split("-")[0])
        patt = int(T["completionAttempts"].split("/")[1])
        mm, ss = T["possessionTime"].split(":")
        tot, pas, rus = int(T["totalYards"]), int(T["netPassingYards"]), int(T["rushingYards"])
        if pas + rus != tot:
            problems.append(f"{t}: pass+rush {pas}+{rus} != total {tot}")
        team_rows.append({
            "Week": week, "Team": t, "Opponent": o, "Venue": g["ha"] or "Neutral", "Pts": pts, "Pass Yds": pas, "Rush Yds": rus,
            "Total Yds": tot, "Turnovers": int(T["turnovers"]), "Result": "W" if pts > opts else "L" if pts < opts else "T",
            "Pts Allowed": opts, "Pass Yds Allowed": int(O["netPassingYards"]), "Rush Yds Allowed": int(O["rushingYards"]),
            "Total Yds Allowed": int(O["totalYards"]), "Takeaways": int(O["turnovers"]), "1H Pts": q[0] + q[1], "2H Pts": q[2] + q[3],
            "TDs": (pts - 3 * fgm - xpm) // 6, "FG Made": fgm, "FG Att": fga, "XP Made": xpm, "XP Att": xpa,
            "Plays": patt + int(T["rushingAttempts"]) + sacks, "1st Downs": int(T["firstDowns"]), "3rd Conv": int(third[0]),
            "3rd Att": int(third[1]), "4th Conv": int(fourth[0]), "4th Att": int(fourth[1]), "Sacks Taken": sacks,
            "Penalties": int(pen[0]), "Pen Yds": int(pen[1]), "TOP (min)": int(mm) + int(ss) / 60, "_score": f"{pts}-{opts}"})
    for (tm, aid, nm), r in players.items():
        o = teams[1] if tm == teams[0] else teams[0]
        if aid in ids:
            name, pos = ids[aid]["name"], ids[aid]["pos"]
        else:
            hit = known.get((tm, norm(ALIAS.get(nm, nm))))
            if hit:
                name, pos = hit
            else:
                try:
                    a = get(ATH.format(a=aid))["athlete"]
                    pos = POSMAP.get(a.get("position", {}).get("abbreviation", ""), None)
                except Exception:
                    pos = None
                    problems.append(f"could not look up position for {nm} ({tm})")
                name = nm
            ids[aid] = {"name": name, "pos": pos}
        if pos not in ("QB", "RB", "WR", "TE"):
            continue     # punters, kickers and defenders on trick plays count in team totals only
        row = {"wk": week, "name": name, "pos": pos, "team": tm, "opp": o}
        for k in ("cmp", "patt", "pyds", "ptd", "int", "ratt", "ryds", "rtd", "tgt", "rec", "recyds", "rectd"):
            row[k] = int(r.get(k, 0))
        player_rows.append(row)
    return team_rows, player_rows


def fetch(week):
    data = json.load(open(os.path.join(HERE, "base.json")))
    sched = {t["name"]: next(x for x in t["schedule"] if x["wk"] == week) for t in data["teams"]}
    evs = week_events(week)
    if not evs or not all(e["final"] for e in evs):
        return None, [f"week {week}: {sum(e['final'] for e in evs)}/{len(evs)} games final"]
    known = known_players()
    ids = json.load(open(NAMES)) if os.path.exists(NAMES) else {}
    team_rows, player_rows, problems = [], [], []
    for e in evs:
        tr, pr = parse_game(get(SUM.format(e=e["id"])), week, sched, known, ids, problems)
        team_rows += tr; player_rows += pr
    by = {r["Team"]: r for r in team_rows}
    for r in team_rows:
        o = by[r["Opponent"]]
        r.update({"1H Pts Allowed": o["1H Pts"], "2H Pts Allowed": o["2H Pts"], "TDs Allowed": o["TDs"],
                  "FG Made Allowed": o["FG Made"], "FG Att Allowed": o["FG Att"], "Plays Allowed": o["Plays"],
                  "1st Downs Allowed": o["1st Downs"], "Opp 3rd Conv": o["3rd Conv"], "Opp 3rd Att": o["3rd Att"],
                  "Opp 4th Conv": o["4th Conv"], "Opp 4th Att": o["4th Att"], "Sacks Made": o["Sacks Taken"]})
    return {"week": week, "source": "ESPN box scores", "team_rows": team_rows, "player_rows": player_rows, "_ids": ids}, problems


def saved_weeks():
    return sorted(int(f[7:-5]) for f in os.listdir(os.path.join(HERE, "weeks")) if f.startswith("supp_wk"))


def main():
    if sys.argv[1] == "--status":
        last = max(saved_weeks())
        print(json.dumps({"saved": last}))
        return
    week = int(sys.argv[1])
    res, problems = fetch(week)
    if res is None:
        print(*problems); sys.exit(2)
    ids = res.pop("_ids")
    if "--check" in sys.argv:
        old = json.load(open(os.path.join(HERE, "weeks", f"supp_wk{week}.json")))
        ot = {r["Team"]: r for r in old["team_rows"]}
        n = 0
        for r in res["team_rows"]:
            for k, v in r.items():
                if k.startswith("_"): continue
                ov = ot[r["Team"]].get(k)
                if (abs(v - ov) > 0.01 if isinstance(v, float) else v != ov):
                    n += 1; print("TEAM", r["Team"], k, "espn", v, "saved", ov)
        op = {(r["team"], r["name"]): r for r in old["player_rows"]}
        npl = {(r["team"], r["name"]): r for r in res["player_rows"]}
        for k in sorted(set(op) | set(npl)):
            a, b = npl.get(k), op.get(k)
            if not a or not b:
                n += 1; print("PLAYER only in", "espn" if a else "saved", k); continue
            d = {f: (a[f], b[f]) for f in a if f not in ("wk",) and a[f] != b[f]}
            if d:
                n += 1; print("PLAYER", k, d)
        print("problems:", problems)
        print(f"week {week}: {n} differences")
        return
    json.dump(res, open(os.path.join(HERE, "weeks", f"supp_wk{week}.json"), "w"), indent=1)
    json.dump(ids, open(NAMES, "w"), indent=0, sort_keys=True)
    print(f"week {week}: {len(res['team_rows'])} team rows, {len(res['player_rows'])} player rows")
    print("problems:", *problems, sep="\n  ")


if __name__ == "__main__":
    main()
