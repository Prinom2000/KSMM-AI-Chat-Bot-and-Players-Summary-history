"""
SofaScore Player Stats Fetcher — Anti-403 Version
===================================================
Library:  curl_cffi  (Chrome TLS fingerprint spoofing)
Install:  pip install curl_cffi

Player: Enzo Fernández (Chelsea) — Player ID: 1106826
"""

import json
import time
from datetime import datetime

try:
    from curl_cffi import requests   # Chrome TLS fingerprint → 403 bypass
    IMPERSONATE = "chrome124"
    print("✓ Using curl_cffi (Chrome fingerprint mode)")
except ImportError:
    import requests                  # Fallback — might get 403
    IMPERSONATE = None
    print("⚠ curl_cffi not found. Run: pip install curl_cffi")
    print("  Falling back to standard requests (may get 403)\n")


# ─────────────────────────────────────────────
# CONFIG — শুধু এই দুটো বদলাও অন্য player এর জন্য
# ─────────────────────────────────────────────
PLAYER_ID   = 974505          # Enzo Fernández (Chelsea)
PLAYER_NAME = "Enzo Fernández"
MAX_PAGES   = 1                # প্রতি page ≈ 10 matches, 5 page = ~50 matches
OUTPUT_FILE = "enzo_match_stats.json"
# ─────────────────────────────────────────────

BASE_URL = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.sofascore.com/",
    "Origin":          "https://www.sofascore.com",
    "Sec-Fetch-Dest":  "empty",
    "Sec-Fetch-Mode":  "cors",
    "Sec-Fetch-Site":  "same-site",
    "sec-ch-ua":        '"Chromium";v="124","Google Chrome";v="124","Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Cache-Control":   "no-cache",
    "Connection":      "keep-alive",
}


# ─────────────────────────────────────────────
def api_get(url: str) -> dict | None:
    """Single GET with curl_cffi (Chrome fingerprint) or fallback requests."""
    try:
        if IMPERSONATE:
            resp = requests.get(
                url,
                headers=HEADERS,
                impersonate=IMPERSONATE,
                timeout=20,
            )
        else:
            resp = requests.get(url, headers=HEADERS, timeout=20)

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            return None          # No more pages
        else:
            print(f"     HTTP {resp.status_code} → {url}")
            return None
    except Exception as e:
        print(f"     Request error: {e}")
        return None


# ─────────────────────────────────────────────
def get_player_events(player_id: int, max_pages: int) -> list:
    """Player এর recent matches list (paginated)."""
    all_events = []
    for page in range(max_pages):
        print(f"  → Page {page}...", end=" ", flush=True)
        url  = f"{BASE_URL}/player/{player_id}/events/last/{page}"
        data = api_get(url)

        if data is None:
            print("done (no more pages)")
            break

        events = data.get("events", [])
        if not events:
            print("empty")
            break

        print(f"{len(events)} matches")
        all_events.extend(events)
        time.sleep(0.5)

    return all_events


# ─────────────────────────────────────────────
def get_match_stats(event_id: int, player_id: int) -> dict:
    """একটি match এ player এর detailed stats।"""
    url  = f"{BASE_URL}/event/{event_id}/player/{player_id}/statistics"
    data = api_get(url)
    return data.get("statistics", {}) if data else {}


# ─────────────────────────────────────────────
def parse_stats(raw: dict) -> dict:
    """Raw SofaScore keys → clean readable dict।"""
    g = lambda key, d=0: raw.get(key, d)
    return {
        # ── Attacking ──────────────────────────
        "goals":             g("goals"),
        "assists":           g("assists"),
        "shots":             g("totalShots"),
        "shotsOnTarget":     g("onTargetScoringAttempt"),
        "xG":                round(g("expectedGoals",   0.0), 2),
        "xA":                round(g("expectedAssists", 0.0), 2),
        "bigChancesCreated": g("bigChanceCreated"),

        # ── Passing ────────────────────────────
        "totalPasses":       g("totalPass"),
        "accuratePasses":    g("accuratePasses"),
        "passAccuracyPct":   round(g("accuratePassesPercentage", 0.0), 1),
        "keyPasses":         g("keyPass"),
        "longBallsAccurate": g("accurateLongBalls"),

        # ── Dribbling ──────────────────────────
        "dribblesAttempted": g("attemptedDribbles"),
        "dribblesSuccessful": g("successfulDribbles"),

        # ── Defending ──────────────────────────
        "tackles":           g("tackles"),
        "interceptions":     g("interceptions"),
        "clearances":        g("clearances"),
        "blockedShots":      g("blockedShots"),

        # ── Duels ──────────────────────────────
        "duelsTotal":        g("totalDuels"),
        "duelsWon":          g("duelsWon"),
        "aerialDuelsWon":    g("aerialDuelsWon"),

        # ── Discipline ─────────────────────────
        "yellowCards":       g("yellowCards"),
        "redCards":          g("redCards"),

        # ── Time & Rating ──────────────────────
        "minutesPlayed":     g("minutesPlayed"),
        "sofascoreRating":   round(g("rating", 0.0), 2),
    }


# ─────────────────────────────────────────────
def parse_event_meta(event: dict) -> dict:
    """Match event → readable metadata।"""
    ts   = event.get("startTimestamp", 0)
    date = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else "Unknown"
    tourn = event.get("tournament", {}).get("name", "Unknown")
    season = event.get("season", {}).get("name", "")
    return {
        "eventId":    event.get("id"),
        "date":       date,
        "competition": f"{tourn} {season}".strip(),
        "homeTeam":   event.get("homeTeam", {}).get("name", "?"),
        "awayTeam":   event.get("awayTeam", {}).get("name", "?"),
        "homeScore":  event.get("homeScore", {}).get("current", "-"),
        "awayScore":  event.get("awayScore", {}).get("current", "-"),
        "round":      event.get("roundInfo", {}).get("name", ""),
        "status":     event.get("status", {}).get("description", ""),
    }


# ─────────────────────────────────────────────
def build_summary(played: list) -> dict:
    """All match stats aggregate করে একটা season summary বানাও।"""
    n = len(played)
    if n == 0:
        return {}

    def total(key):
        return sum(r["stats"].get(key, 0) for r in played)

    def avg(key):
        vals = [r["stats"].get(key, 0) for r in played if r["stats"].get(key, 0) > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0

    return {
        "player":         PLAYER_NAME,
        "playerId":       PLAYER_ID,
        "fetchedAt":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "appearances":    n,
        "minutesPlayed":  total("minutesPlayed"),
        "goals":          total("goals"),
        "assists":        total("assists"),
        "shots":          total("shots"),
        "shotsOnTarget":  total("shotsOnTarget"),
        "xG":             round(total("xG"), 2),
        "xA":             round(total("xA"), 2),
        "keyPasses":      total("keyPasses"),
        "bigChancesCreated": total("bigChancesCreated"),
        "tackles":        total("tackles"),
        "interceptions":  total("interceptions"),
        "clearances":     total("clearances"),
        "yellowCards":    total("yellowCards"),
        "redCards":       total("redCards"),
        "avgRating":      avg("sofascoreRating"),
        "avgPassAccuracy": avg("passAccuracyPct"),
    }


# ─────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"  SofaScore Player Stats Fetcher")
    print(f"  Player : {PLAYER_NAME}  (ID: {PLAYER_ID})")
    print(f"{'='*55}\n")

    # 1. Match list
    print("[1/3] Fetching recent match list...")
    events = get_player_events(PLAYER_ID, MAX_PAGES)
    print(f"\n  ✓ Total matches found: {len(events)}\n")

    if not events:
        print("❌ No events found. Exiting.")
        return

    # 2. Per-match stats
    print("[2/3] Fetching per-match statistics...")
    results = []

    for i, event in enumerate(events):
        meta = parse_event_meta(event)
        label = f"{meta['homeTeam']} {meta['homeScore']}-{meta['awayScore']} {meta['awayTeam']}"
        print(f"  [{i+1:>2}/{len(events)}] {meta['date']}  {label[:42]:<42}", end=" ")

        raw   = get_match_stats(meta["eventId"], PLAYER_ID)
        stats = parse_stats(raw) if raw else {}

        if stats:
            print(f"⭐{stats['sofascoreRating']}  {stats['minutesPlayed']}'")
        else:
            print("— no stats")

        results.append({"match": meta, "stats": stats})
        time.sleep(0.4)

    # 3. Summary
    played  = [r for r in results if r["stats"]]
    summary = build_summary(played)

    output = {"summary": summary, "matches": results}

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    s = summary
    print(f"\n{'='*55}")
    print(f"  SUMMARY — {PLAYER_NAME}")
    print(f"{'='*55}")
    print(f"  Appearances      : {s.get('appearances', 0)}")
    print(f"  Minutes Played   : {s.get('minutesPlayed', 0)}")
    print(f"  Goals            : {s.get('goals', 0)}")
    print(f"  Assists          : {s.get('assists', 0)}")
    print(f"  xG               : {s.get('xG', 0)}")
    print(f"  Shots            : {s.get('shots', 0)}  (On Target: {s.get('shotsOnTarget', 0)})")
    print(f"  Key Passes       : {s.get('keyPasses', 0)}")
    print(f"  Big Chances Crtd : {s.get('bigChancesCreated', 0)}")
    print(f"  Tackles          : {s.get('tackles', 0)}")
    print(f"  Interceptions    : {s.get('interceptions', 0)}")
    print(f"  Yellow Cards     : {s.get('yellowCards', 0)}")
    print(f"  Red Cards        : {s.get('redCards', 0)}")
    print(f"  Avg Rating       : {s.get('avgRating', 0)}")
    print(f"  Avg Pass Acc.    : {s.get('avgPassAccuracy', 0)}%")
    print(f"{'='*55}")
    print(f"\n  ✓ Full data saved → {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()