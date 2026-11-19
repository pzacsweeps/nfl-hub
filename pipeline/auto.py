"""Decides what the scheduled GitHub Actions runs should do. All times are UK time (Europe/London).

    python3 pipeline/auto.py stats      -> is a finished week waiting to be added? (Tuesday mornings)
    python3 pipeline/auto.py injuries   -> which injury slot is due now, if any:
                                            thu      Thursday 22:00
                                            sunam    Sunday 09:00 (also saves the first Sunday kickoff)
                                            pregame  Sunday, 30 minutes before the first kickoff
    python3 pipeline/auto.py mark <slot> -> record that a slot ran today

Decisions go to $GITHUB_OUTPUT. AUTO_NOW=2026-11-22T08:55:00Z overrides the clock for testing.
"""
import json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "auto_state.json")
LON = ZoneInfo("Europe/London")
SEASON = int(os.environ.get("NFL_SEASON", "2026"))
SB = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def now():
    o = os.environ.get("AUTO_NOW")
    return datetime.strptime(o, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if o else datetime.now(timezone.utc)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (nfl-hub)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def emit(**kv):
    print(" ".join(f"{k}={v}" for k, v in kv.items()))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={str(v).lower() if isinstance(v, bool) else v}\n")


def state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save(st):
    json.dump(st, open(STATE, "w"), indent=1, sort_keys=True)


def saved_week():
    return max(int(f[7:-5]) for f in os.listdir(os.path.join(HERE, "weeks")) if f.startswith("supp_wk"))


def first_sunday_kickoff(t):
    """Earliest kickoff today (UK date) from ESPN's current-week scoreboard."""
    sb = get(SB)
    today = t.astimezone(LON).date()
    ks = sorted(datetime.strptime(e["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                for e in sb.get("events", []))
    ks = [k for k in ks if k.astimezone(LON).date() == today]
    return ks[0] if ks else None


def main():
    cmd = sys.argv[1]
    t = now(); lt = t.astimezone(LON); st = state()
    if cmd == "mark":
        st.setdefault("done", {})[sys.argv[2]] = lt.date().isoformat()
        st.setdefault("lastRun", {})[sys.argv[2]] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        save(st); print("marked", sys.argv[2]); return

    if cmd == "stats":
        nxt = saved_week() + 1
        if nxt > 18:
            emit(due=False, week=0); return
        sb = get(f"{SB}?seasontype=2&week={nxt}&dates={SEASON}")
        evs = sb.get("events", [])
        done = [e for e in evs if e["status"]["type"].get("completed")]
        due = bool(evs) and len(done) == len(evs)
        print(f"week {nxt}: {len(done)}/{len(evs)} games final")
        emit(due=due, week=nxt); return

    if cmd == "injuries":
        done = st.get("done", {})
        today = lt.date().isoformat()
        wd, hm = lt.weekday(), lt.hour * 60 + lt.minute      # Mon=0 ... Sun=6
        slot, label = None, ""
        if wd == 3 and 21 * 60 + 45 <= hm < 23 * 60 + 30 and done.get("thu") != today:
            slot, label = "thu", "Thursday evening report"
        elif wd == 6:
            if 8 * 60 + 45 <= hm < 11 * 60 and done.get("sunam") != today:
                slot, label = "sunam", "Sunday morning"
                try:
                    k = first_sunday_kickoff(t)
                    st["sunday"] = {"date": today, "firstKick": k.strftime("%Y-%m-%dT%H:%M:%SZ") if k else None}
                    save(st)
                except Exception as e:
                    print("could not read kickoff times:", e)
            elif done.get("pregame") != today:
                sd = st.get("sunday", {})
                if sd.get("date") != today:
                    k = first_sunday_kickoff(t)
                    sd = {"date": today, "firstKick": k.strftime("%Y-%m-%dT%H:%M:%SZ") if k else None}
                    st["sunday"] = sd; save(st)
                if sd.get("firstKick"):
                    k = datetime.strptime(sd["firstKick"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if k - timedelta(minutes=50) <= t < k - timedelta(minutes=5):
                        slot, label = "pregame", f"pre-game, first kickoff {k.astimezone(LON):%H:%M}"
                    else:
                        print(f"pre-game not due (first kickoff {k.astimezone(LON):%H:%M} UK)")
        emit(due=bool(slot), slot=slot or "none", label=label.replace(" ", "_")); return

    sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
