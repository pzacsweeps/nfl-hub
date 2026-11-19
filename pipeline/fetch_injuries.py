"""Rebuild pipeline/injuries.json from the official NFL.com injury report and the CBS Sports injury page.

NFL.com  -> this week's official practice participation and game statuses
CBS      -> IR / PUP / NFI / suspended lists with expected return weeks, late downgrades and IR moves
ESPN     -> which games are already played this week and which teams are on bye (scoreboard),
            and the injured lists if CBS cannot be read (team rosters)

    python3 pipeline/fetch_injuries.py [--label "Thu evening"]
Test with saved pages: NFL_HTML=nfl.html CBS_HTML=cbs.html ESPN_SB=sb.json python3 pipeline/fetch_injuries.py
"""
import html as H, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
    LON = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover
    LON = timezone.utc

HERE = os.path.dirname(os.path.abspath(__file__))
SEASON = int(os.environ.get("NFL_SEASON", "2026"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
PRACTICE = {"Did Not Participate In Practice": "DNP", "Limited Participation in Practice": "Limited",
            "Full Participation in Practice": "Full"}
POS = {"SAF": "S", "FS": "S", "SS": "S", "OT": "T", "OL": "T", "DL": "DT", "NT": "DT", "MLB": "LB", "OLB": "LB", "ILB": "LB", "DB": "CB", "PK": "K"}
ALIAS = {"kamren curl": "kam curl", "christopher brooks": "chris brooks", "jake hummel": "jacob hummel"}
STARS = {
    "Nick Bosa", "Trent Williams", "Puka Nacua", "T.J. Watt", "Cameron Heyward", "Jalen Ramsey", "Saquon Barkley", "Jalen Carter",
    "Justin Jefferson", "Jonathan Taylor", "Travis Kelce", "Brock Bowers", "Nico Collins", "Will Anderson Jr.", "Pat Surtain II",
    "Sauce Gardner", "Trent McDuffie", "Kerby Joseph", "Laremy Tunsil", "Rashawn Slater", "Christian Darrisaw", "Dexter Lawrence",
    "Aaron Donald", "Bijan Robinson", "Kobie Turner", "Davante Adams", "Mike Evans", "Rashee Rice", "Deebo Samuel Sr.",
    "DeForest Buckner", "Lane Johnson", "Penei Sewell", "Jahmyr Gibbs", "Amon-Ra St. Brown", "Ja'Marr Chase", "Josh Allen",
    "Ed Oliver", "Derwin James", "Fred Warner", "George Kittle", "Tyler Warren", "Edgerrin Cooper", "Micah Parsons", "Myles Garrett",
    "Lamar Jackson", "Patrick Mahomes", "Joe Burrow", "Christian McCaffrey", "CeeDee Lamb", "Jaxon Smith-Njigba", "Malik Nabers",
}
TIER_RANK = {"reserve": 0, "backup": 1, "starter": 2, "star": 3}


def get(url, as_json=False, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(4 * (i + 1))


def txt(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm(n):
    n = n.lower().replace(".", "").replace("'", "").replace("’", "")
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return ALIAS.get(n, n)


# ---------------- sources ----------------
def nfl_report(page):
    m = re.search(r"Week (\d+) of the (\d{4})", page)
    week = int(m.group(1)) if m else None
    start = page.find("nfl-o-injury-report__wrap")
    if start < 0:
        raise RuntimeError("NFL.com injury report not found on the page")
    page = page[start:]
    out, games = {}, []
    for day_block in re.split(r'<h2 class="d3-o-section-title">', page)[1:]:
        day = txt(day_block[:day_block.find("</h2>")])
        for unit in day_block.split('<section class="nfl-o-injury-report__unit">')[1:]:
            tm = re.search(r'nfl-c-matchup-strip__date-time">(.*?)<', unit)
            names = [txt(x) for x in re.findall(r'nfl-c-matchup-strip__team-fullname"[^>]*>(.*?)</a>', unit, re.S)]
            games.append({"day": day, "time": tm.group(1).strip() if tm else "", "teams": names})
            titles = [txt(x) for x in re.findall(r'nfl-t-stats__title.*?<span>(.*?)</span>', unit, re.S)]
            tables = re.findall(r"<tbody>(.*?)</tbody>", unit, re.S)
            for nick, tb in zip(titles, tables):
                for tr in re.findall(r"<tr>(.*?)</tr>", tb, re.S):
                    td = [txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                    if len(td) >= 5 and td[0]:
                        out.setdefault(nick, []).append({"player": td[0], "pos": td[1], "injury": td[2],
                                                         "prac": PRACTICE.get(td[3], td[3]), "status": td[4], "day": day})
    return week, out, games


def cbs_report(page):
    out = {}
    for blk in page.split('class="TableBaseWrapper"')[1:]:
        tm = re.search(r'class="TeamName"><a[^>]*>(.*?)</a>', blk, re.S)
        if not tm:
            continue
        team = txt(tm.group(1))
        for tr in blk.split("TableBase-bodyTr")[1:]:
            tr = tr.split("</tr>")[0]
            name = re.search(r'CellPlayerName--long".*?<a[^>]*>(.*?)</a>', tr, re.S)
            tds = [txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if not name or len(tds) < 5:
                continue
            out.setdefault(team, []).append({"player": txt(name.group(1)), "pos": POS.get(tds[1], tds[1]),
                                             "date": tds[2], "injury": tds[3], "s": tds[4]})
    if sum(len(v) for v in out.values()) < 100:
        raise RuntimeError("CBS page parsed too few rows")
    return out


def espn_week(week):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={week}&dates={SEASON}"
    sb = json.load(open(os.environ["ESPN_SB"])) if os.environ.get("ESPN_SB") else get(url, True)
    games = []
    for e in sb.get("events", []):
        comp = e["competitions"][0]
        games.append({"date": e["date"], "state": e["status"]["type"]["state"],
                      "teams": [c["team"]["displayName"] for c in comp["competitors"]]})
    byes = [t["displayName"] for t in sb.get("week", {}).get("teamsOnBye", [])]
    return games, byes


def espn_rosters():
    """Fallback injured lists: {team: [{player,pos,status,date}]}"""
    out = {}
    for tid in list(range(1, 31)) + [33, 34]:
        r = get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{tid}/roster", True)
        team = r["team"]["displayName"]
        for a in (x for g in r.get("athletes", []) for x in g.get("items", [])):
            inj = (a.get("injuries") or [None])[0]
            if inj and inj.get("status") in ("Injured Reserve", "Out", "Suspension"):
                out.setdefault(team, []).append({"player": a["displayName"], "pos": POS.get(a.get("position", {}).get("abbreviation", ""), a.get("position", {}).get("abbreviation", "")),
                                                 "status": inj["status"], "date": inj.get("date", "")})
    return out


# ---------------- roles ----------------
def tier_fn():
    base = json.load(open(os.path.join(HERE, "base.json")))
    data = json.load(open(os.path.join(HERE, "data.json")))
    old_imp = {(t["name"], x["player"]): x.get("imp") for t in base["teams"] for x in t.get("injuries", []) if x.get("imp")}
    depth = {t["name"]: t.get("depth", {}) for t in base["teams"]}
    prod = {}
    for p in data["players"]:
        n = len(p["games"]) or 1
        s = lambda k: sum(g[k] for g in p["games"]) / n
        prod[(p["team"], norm(p["name"]))] = (p["pos"], s("ryds") + s("recyds"), s("recyds"))

    def tier(team, player, pos):
        best = "reserve"
        def up(t):
            nonlocal best
            if TIER_RANK[t] > TIER_RANK[best]:
                best = t
        imp = old_imp.get((team, player))
        if imp == 5: up("star")
        elif imp == 4: up("starter")
        elif imp in (2, 3): up("backup")
        if player in STARS: up("star")
        d = depth.get(team, {}).get(player)
        if d:
            up(("star" if d["slot"] == "QB" else "starter") if d["role"] == "starter" else "backup")
        pr = prod.get((team, norm(player)))
        if pr:
            ppos, scrim, rec = pr
            if (ppos == "RB" and scrim >= 40) or (ppos in ("WR", "TE") and rec >= 30): up("starter")
            elif scrim >= 10: up("backup")
        return best
    return tier


# ---------------- merge ----------------
def cbs_status(c, week):
    s = c["s"]
    m = re.search(r"Expected Return - Week (\d+)", s)
    r = int(m.group(1)) if m else None
    ret = (f"earliest return Wk {r}" if r and r > week else "eligible to return" if r else "no return date")
    if re.match(r"^(IR\b|Injured Reserve)", s):
        return "IR · " + ret
    if s.startswith("Physically Unable"):
        return "PUP · " + ret
    if s.startswith("NFI") or s.startswith("Non-Football"):
        return "NFI list"
    if s.lower().startswith("susp"):
        return "Suspended" + (f" · until Wk {r}" if r else "")
    if re.search(r"out for (the )?season", s, re.I):
        return "Out for the season"
    m = re.search(r"(Questionable|Doubtful|Out|Inactive) for Week (\d+)", s)
    if m:
        st, w = m.group(1), int(m.group(2))
        if w == week:
            return st.upper()
        if w == week + 1:
            return f"Hurt · listed {st.lower()} for Wk {w}"
    return None  # an old week: stale


def main():
    now = datetime.now(timezone.utc)
    nfl_page = open(os.environ["NFL_HTML"]).read() if os.environ.get("NFL_HTML") else get("https://www.nfl.com/injuries/")
    week, nfl, nfl_games = nfl_report(nfl_page)
    if not week:
        sys.exit("could not read the week from NFL.com")
    data = json.load(open(os.path.join(HERE, "base.json")))
    TEAMS = [t["name"] for t in data["teams"]]
    sched = {t["name"]: next((x for x in t["schedule"] if x["wk"] == week), {}) for t in data["teams"]}
    NICK = {t.split()[-1]: t for t in TEAMS}
    CITY = {t.rsplit(" ", 1)[0]: t for t in TEAMS}
    CITY.update({"L.A. Chargers": "Los Angeles Chargers", "L.A. Rams": "Los Angeles Rams", "N.Y. Giants": "New York Giants",
                 "N.Y. Jets": "New York Jets", "San Francisco": "San Francisco 49ers", "Washington": "Washington Commanders"})
    weekly = {NICK[k]: v for k, v in nfl.items() if k in NICK}
    try:
        egames, ebyes = espn_week(week)
    except Exception as e:
        print("ESPN scoreboard unavailable:", e); egames, ebyes = [], []
    played = {t for g in egames if g["state"] == "post" for t in g["teams"]}
    live = {t for g in egames if g["state"] == "in" for t in g["teams"]}
    byes = set(ebyes) or {t for t in TEAMS if sched[t].get("opp") in (None, "BYE")}
    src = "CBS Sports"
    try:
        cbs_page = open(os.environ["CBS_HTML"]).read() if os.environ.get("CBS_HTML") else get("https://www.cbssports.com/nfl/injuries/")
        cbs = {CITY.get(k, k): v for k, v in cbs_report(cbs_page).items()}
    except Exception as e:
        print("CBS unavailable, using ESPN rosters for the injured lists:", e)
        src = "ESPN"
        cbs = {}
        for team, rows in espn_rosters().items():
            for r in rows:
                s = {"Injured Reserve": "IR. Injured Reserve", "Suspension": "Suspended", "Out": f"Out for Week {week}"}[r["status"]]
                cbs.setdefault(team, []).append({"player": r["player"], "pos": r["pos"], "date": r["date"], "injury": "", "s": s})
    prev = json.load(open(os.path.join(HERE, "injuries.json")))
    prev_inj = {(t, norm(r["player"])): r.get("injury") for t, v in prev.items() for r in v["injuries"] if r.get("injury")}
    prev_ir = {(t, norm(r["player"])) for t, v in prev.items() for r in v["injuries"] if r["status"].startswith(("IR", "Season"))}
    tier = tier_fn()
    out = {}
    for t in TEAMS:
        C = {norm(c["player"]): c for c in cbs.get(t, [])}
        rows = []
        W = weekly.get(t, [])
        status_set = any(r["status"] for r in W)
        for r in W:
            c = C.pop(norm(r["player"]), None)
            cs = cbs_status(c, week) if c else None
            st = r["status"].upper() if r["status"] else None
            if t in played or t in live:
                if cs and cs.startswith(("IR", "PUP", "NFI", "Hurt", "Suspended", "Out for")):
                    st = cs
                elif st:
                    st = f"Wk {week}: {st.title()}"
                else:
                    continue
            elif cs and cs.startswith(("IR", "PUP")) and "eligible" in cs and st:
                st = f"{st} · returning from {cs[:3].strip()}"
            elif cs and (cs.startswith(("IR", "NFI", "Suspended", "Out for")) or (cs == "OUT" and st != "OUT")):
                st = cs
            elif not st:
                if status_set:
                    st = "No designation" + (" · DNP (not injury-related or rest)" if r["prac"] == "DNP" and not c else "")
                else:
                    st = f"Practice: {r['prac']}" if r["prac"] else "Listed"
            rows.append({"player": r["player"], "pos": r["pos"], "injury": r["injury"] or (c or {}).get("injury") or prev_inj.get((t, norm(r["player"]))), "status": st})
        for k, c in C.items():
            st = cbs_status(c, week)
            if not st:
                continue
            if st == "INACTIVE":
                if "Coach" in c["injury"]:
                    continue
                st = f"Wk {week}: Inactive"
            if (t in played or t in live) and st in ("OUT", "DOUBTFUL", "QUESTIONABLE"):
                st = f"Wk {week}: {st.title()}"
            rows.append({"player": c["player"], "pos": c["pos"], "injury": c["injury"] or prev_inj.get((t, k)), "status": st})
        for r in rows:
            if r["status"].startswith("IR") and c_is_new(cbs.get(t, []), r["player"], now) and (t, norm(r["player"])) not in prev_ir:
                r["status"] += " · placed this week"
            r["tier"] = tier(t, r["player"], r["pos"])
            if not r["injury"]:
                r["injury"] = None
        g = sched[t]
        day = next((x["day"].title() for x in nfl_games if any(n and t.endswith(n) for n in x["teams"])), "")
        if t in byes:
            title = f"Bye in Week {week} · injured lists + early Week {week + 1} notes"
        elif t in played:
            title = f"Week {week} played · Week {week + 1} reports start next week"
        elif t in live:
            title = f"Week {week} · game in progress"
        elif status_set:
            title = f"Week {week} · final game statuses · {g.get('date') or day} · inactives 90 min before kickoff"
        elif W:
            last_day = W[0]["day"]
            title = f"Week {week} · latest practice report · game statuses due before {g.get('date') or day.title()}"
        else:
            title = f"Week {week} · no official report yet · injured lists only" + (f" · game {g.get('date')}" if g.get("date") else "")
        out[t] = {"title": title, "injuries": rows}
    json.dump(out, open(os.path.join(HERE, "injuries.json"), "w"), indent=0)
    lt = now.astimezone(LON)
    label = (os.environ.get("INJ_LABEL") or "").replace("_", " ")
    stamp = lt.strftime("%a %-d %b, %H:%M") + " (UK)"
    meta = json.load(open(os.path.join(HERE, "meta.json")))
    meta.update({"injUpdated": f"{stamp} · Week {week}{' · ' + label if label else ''} · NFL.com official report + {src} injured lists",
                 "injUpdatedShort": lt.strftime("%a %-d %b"), "injWeek": week})
    json.dump(meta, open(os.path.join(HERE, "meta.json"), "w"))
    from collections import Counter
    print(f"week {week}: {sum(len(v['injuries']) for v in out.values())} entries; on the NFL.com report: {len(weekly)} teams;",
          f"played: {len(played)}, byes: {len(byes)}, lists from {src}")
    print(Counter(r["status"].split(" ")[0] for v in out.values() for r in v["injuries"]))


def c_is_new(rows, player, now):
    """CBS row dated within the last 6 days."""
    for c in rows:
        if c["player"] == player:
            try:
                d = datetime.strptime(f"{c['date']} {now.year}", "%a, %b %d %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    d = datetime.strptime(f"{c['date']} {now.year}", "%b %d %Y").replace(tzinfo=timezone.utc)
                except ValueError:
                    return False
            if d > now:
                d = d.replace(year=d.year - 1)
            return (now - d).days <= 6
    return False


if __name__ == "__main__":
    main()
