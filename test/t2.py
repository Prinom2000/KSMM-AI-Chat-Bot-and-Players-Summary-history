"""
SofaScore Player Stats — Last 7 Days Only
==========================================
Install: pip install curl_cffi
Run:     python sofascore_player_stats.py
"""

import json
import time
from datetime import datetime, timezone, timedelta

try:
    from curl_cffi import requests
    IMPERSONATE = "chrome124"
except ImportError:
    import requests
    IMPERSONATE = None
    print("⚠ Run: pip install curl_cffi\n")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
PLAYER_ID   = 974505
PLAYER_NAME = ""
DAYS_BACK   = 7           # শুধু last N days এর matches
OUTPUT_FILE = "enzo_last7days.json"
# ─────────────────────────────────────────────

BASE_URL = "https://api.sofascore.com/api/v1"
HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Referer":          "https://www.sofascore.com/",
    "Origin":           "https://www.sofascore.com",
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-site",
}

CUTOFF = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)


def api_get(url):
    try:
        if IMPERSONATE:
            r = requests.get(url, headers=HEADERS, impersonate=IMPERSONATE, timeout=20)
        else:
            r = requests.get(url, headers=HEADERS, timeout=20)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def get_recent_events(player_id):
    """
    Page 0 থেকে শুরু করো।
    Event গুলো newest-first আসে।
    যখনই CUTOFF এর আগের match পাবে, বন্ধ করো।
    """
    matches = []
    for page in range(10):  # max 10 pages safety limit
        data = api_get(f"{BASE_URL}/player/{player_id}/events/last/{page}")
        if not data:
            break

        events = data.get("events", [])
        if not events:
            break

        found_old = False
        for ev in events:
            ts = ev.get("startTimestamp", 0)
            match_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if match_dt >= CUTOFF:
                matches.append(ev)
            else:
                found_old = True  # এর চেয়ে পুরনো সব বাদ

        if found_old:
            break  # আর page দরকার নেই

        time.sleep(0.4)

    return matches


def get_match_stats(event_id, player_id):
    data = api_get(f"{BASE_URL}/event/{event_id}/player/{player_id}/statistics")
    return data.get("statistics", {}) if data else {}


def parse_stats(raw):
    g = lambda k, d=0: raw.get(k, d)
    return {
        "goals":              g("goals"),
        "assists":            g("assists"),
        "shots":              g("totalShots"),
        "shotsOnTarget":      g("onTargetScoringAttempt"),
        "xG":                 round(g("expectedGoals", 0.0), 2),
        "xA":                 round(g("expectedAssists", 0.0), 2),
        "keyPasses":          g("keyPass"),
        "totalPasses":        g("totalPass"),
        "accuratePasses":     g("accuratePasses"),
        "passAccuracyPct":    round(g("accuratePassesPercentage", 0.0), 1),
        "bigChancesCreated":  g("bigChanceCreated"),
        "dribblesSuccessful": g("successfulDribbles"),
        "dribblesAttempted":  g("attemptedDribbles"),
        "tackles":            g("tackles"),
        "interceptions":      g("interceptions"),
        "clearances":         g("clearances"),
        "blockedShots":       g("blockedShots"),
        "duelsWon":           g("duelsWon"),
        "duelsTotal":         g("totalDuels"),
        "aerialDuelsWon":     g("aerialDuelsWon"),
        "yellowCards":        g("yellowCards"),
        "redCards":           g("redCards"),
        "minutesPlayed":      g("minutesPlayed"),
        "sofascoreRating":    round(g("rating", 0.0), 2),
    }


def parse_meta(ev):
    ts = ev.get("startTimestamp", 0)
    date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "eventId":     ev.get("id"),
        "date":        date,
        "competition": ev.get("tournament", {}).get("name", "?"),
        "homeTeam":    ev.get("homeTeam", {}).get("name", "?"),
        "awayTeam":    ev.get("awayTeam", {}).get("name", "?"),
        "homeScore":   ev.get("homeScore", {}).get("current", "-"),
        "awayScore":   ev.get("awayScore", {}).get("current", "-"),
        "status":      ev.get("status", {}).get("description", ""),
    }


def main():
    print(f"\n{'='*52}")
    print(f"  {PLAYER_NAME} — Last {DAYS_BACK} Days Stats")
    print(f"  Since: {CUTOFF.strftime('%Y-%m-%d')}")
    print(f"{'='*52}\n")

    print("Fetching recent matches...")
    events = get_recent_events(PLAYER_ID)
    print(f"✓ Found {len(events)} match(es) in last {DAYS_BACK} days\n")

    if not events:
        print("No matches found in this period.")
        return

    results = []
    for i, ev in enumerate(events):
        meta  = parse_meta(ev)
        label = f"{meta['homeTeam']} {meta['homeScore']}-{meta['awayScore']} {meta['awayTeam']}"
        print(f"  [{i+1}/{len(events)}] {meta['date']}  {label}")
        print(f"         Competition: {meta['competition']}")

        raw   = get_match_stats(meta["eventId"], PLAYER_ID)
        stats = parse_stats(raw) if raw else {}

        if stats:
            print(f"         Rating: ⭐{stats['sofascoreRating']}  |  "
                  f"{stats['minutesPlayed']}' played  |  "
                  f"Goals: {stats['goals']}  Assists: {stats['assists']}  "
                  f"xG: {stats['xG']}")
            print(f"         Passes: {stats['accuratePasses']}/{stats['totalPasses']} "
                  f"({stats['passAccuracyPct']}%)  |  "
                  f"KeyPasses: {stats['keyPasses']}  |  "
                  f"Tackles: {stats['tackles']}  Interceptions: {stats['interceptions']}")
            print(f"         YC: {stats['yellowCards']}  RC: {stats['redCards']}\n")
        else:
            print("         No stats available\n")
            stats = {}

        results.append({"match": meta, "stats": stats})
        time.sleep(0.4)

    # Summary
    played = [r for r in results if r["stats"]]
    n = len(played)

    if n > 0:
        total = lambda k: sum(r["stats"].get(k, 0) for r in played)
        avg   = lambda k: round(
            sum(r["stats"].get(k, 0) for r in played if r["stats"].get(k, 0) > 0)
            / max(1, sum(1 for r in played if r["stats"].get(k, 0) > 0)), 2
        )

        summary = {
            "player":        PLAYER_NAME,
            "playerId":      PLAYER_ID,
            "period":        f"Last {DAYS_BACK} days",
            "from":          CUTOFF.strftime("%Y-%m-%d"),
            "fetchedAt":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "appearances":   n,
            "minutesPlayed": total("minutesPlayed"),
            "goals":         total("goals"),
            "assists":       total("assists"),
            "shots":         total("shots"),
            "shotsOnTarget": total("shotsOnTarget"),
            "xG":            round(total("xG"), 2),
            "xA":            round(total("xA"), 2),
            "keyPasses":     total("keyPasses"),
            "tackles":       total("tackles"),
            "interceptions": total("interceptions"),
            "yellowCards":   total("yellowCards"),
            "redCards":      total("redCards"),
            "avgRating":     avg("sofascoreRating"),
            "avgPassAccuracyPct": avg("passAccuracyPct"),
        }
    else:
        summary = {}

    output = {"summary": summary, "matches": results}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if summary:
        s = summary
        print(f"{'='*52}")
        print(f"  SUMMARY (Last {DAYS_BACK} days)")
        print(f"{'='*52}")
        print(f"  Appearances   : {s['appearances']}")
        print(f"  Minutes       : {s['minutesPlayed']}")
        print(f"  Goals         : {s['goals']}")
        print(f"  Assists       : {s['assists']}")
        print(f"  xG / xA       : {s['xG']} / {s['xA']}")
        print(f"  Shots (OnTgt) : {s['shots']} ({s['shotsOnTarget']})")
        print(f"  Key Passes    : {s['keyPasses']}")
        print(f"  Tackles       : {s['tackles']}")
        print(f"  Interceptions : {s['interceptions']}")
        print(f"  Yellow / Red  : {s['yellowCards']} / {s['redCards']}")
        print(f"  Avg Rating    : {s['avgRating']}")
        print(f"  Avg Pass Acc  : {s['avgPassAccuracyPct']}%")
        print(f"{'='*52}")

    print(f"\n✓ Saved → {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()