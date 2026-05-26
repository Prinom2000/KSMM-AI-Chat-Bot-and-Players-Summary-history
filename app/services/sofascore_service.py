import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import httpx

# ── curl_cffi: use only if a pre-built wheel is available ──────────────────
# On Render (read-only FS) compiling from source fails.
# Safe check: import the actual Session class, not just the top-level package.
_USE_CURL = False
try:
    from curl_cffi.requests import AsyncSession as _CurlSession  # pre-built wheel
    _USE_CURL = True
except Exception:
    pass  # fall through to httpx

BASE_URL = "https://api.sofascore.com/api/v1"

# Full browser-like headers — reduces 403 risk even with httpx
HEADERS = {
    "User-Agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
    "Accept":             "application/json, text/plain, */*",
    "Accept-Language":    "en-US,en;q=0.9",
    "Accept-Encoding":    "gzip, deflate, br",
    "Referer":            "https://www.sofascore.com/",
    "Origin":             "https://www.sofascore.com",
    "Sec-Fetch-Dest":     "empty",
    "Sec-Fetch-Mode":     "cors",
    "Sec-Fetch-Site":     "same-site",
    "sec-ch-ua":          '"Chromium";v="124","Google Chrome";v="124","Not-A.Brand";v="99"',
    "sec-ch-ua-mobile":   "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Cache-Control":      "no-cache",
    "Connection":         "keep-alive",
}


class SofaScoreService:

    # ─────────────────────────────────────────────────────────────
    # Core HTTP
    # Priority 1 — curl_cffi  (Chrome TLS fingerprint, best anti-403)
    # Priority 2 — httpx      (standard async, works on Render)
    # ─────────────────────────────────────────────────────────────
    async def _api_get(self, path: str) -> dict[str, Any] | None:
        url = BASE_URL + path
        try:
            if _USE_CURL:
                async with _CurlSession(
                    impersonate="chrome124", headers=HEADERS, timeout=20
                ) as s:
                    r = await s.get(url)
            else:
                async with httpx.AsyncClient(
                    timeout=20.0, headers=HEADERS, follow_redirects=True
                ) as client:
                    r = await client.get(url)

            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────
    # Player info
    # ─────────────────────────────────────────────────────────────
    async def get_player_info(self, player_id: int) -> dict[str, Any]:
        data = await self._api_get(f"/player/{player_id}")
        if not isinstance(data, dict):
            return {"playerId": player_id, "playerName": "Unknown Player"}
        p = data.get("player") or data  # some endpoints wrap under "player"
        return {
            "playerId":   player_id,
            "playerName": p.get("name") or p.get("commonName") or p.get("fullName") or "Unknown Player",
            "country":    (p.get("country") or {}).get("name") or p.get("countryName"),
            "position":   p.get("position") or p.get("role"),
            "team":       (p.get("team") or {}).get("name"),
            "dateOfBirth": p.get("dateOfBirthTimestamp"),
        }

    # ─────────────────────────────────────────────────────────────
    # Recent events — football/basketball/tennis  (player endpoint)
    # ─────────────────────────────────────────────────────────────
    async def get_recent_events(self, player_id: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        matches: list[dict[str, Any]] = []

        for page in range(10):
            data = await self._api_get(f"/player/{player_id}/events/last/{page}")
            if not data:
                break
            events = data.get("events") or []
            if not events:
                break

            found_old = False
            for ev in events:
                ts = ev.get("startTimestamp")
                if not ts:
                    continue
                event_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if event_dt < cutoff:
                    found_old = True
                    continue
                ev["_eventDateIso"] = event_dt.isoformat()
                matches.append(ev)

            if found_old:
                break
            await asyncio.sleep(0.25)

        return matches

    # ─────────────────────────────────────────────────────────────
    # Recent events — MMA  (SofaScore stores fighters as "teams")
    # Endpoint: /team/{fighter_id}/events/last/{page}
    # ─────────────────────────────────────────────────────────────
    async def get_recent_mma_events(self, fighter_id: int) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        matches: list[dict[str, Any]] = []

        for page in range(10):
            # MMA fighters are "teams" in SofaScore
            data = await self._api_get(f"/team/{fighter_id}/events/last/{page}")
            if not data:
                break
            events = data.get("events") or []
            if not events:
                break

            found_old = False
            for ev in events:
                ts = ev.get("startTimestamp")
                if not ts:
                    continue
                event_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if event_dt < cutoff:
                    found_old = True
                    continue
                ev["_eventDateIso"] = event_dt.isoformat()
                ev["_fighterId"]    = fighter_id   # carry fighter id for result calc
                matches.append(ev)

            if found_old:
                break
            await asyncio.sleep(0.25)

        return matches

    # ─────────────────────────────────────────────────────────────
    # MMA fighter info  (team endpoint)
    # ─────────────────────────────────────────────────────────────
    async def get_fighter_info(self, fighter_id: int) -> dict[str, Any]:
        data = await self._api_get(f"/team/{fighter_id}")
        if not isinstance(data, dict):
            return {"playerId": fighter_id, "playerName": "Unknown Fighter"}
        t = data.get("team") or data
        return {
            "playerId":   fighter_id,
            "playerName": t.get("name") or t.get("fullName") or "Unknown Fighter",
            "country":    (t.get("country") or {}).get("name"),
            "sport":      "mma",
        }

    # ─────────────────────────────────────────────────────────────
    # Per-match statistics
    # ─────────────────────────────────────────────────────────────
    async def get_match_statistics(self, event_id: int, player_id: int) -> dict[str, Any]:
        data = await self._api_get(f"/event/{event_id}/player/{player_id}/statistics")
        if not isinstance(data, dict):
            return {}
        return data.get("statistics") or {}

    async def get_mma_fight_statistics(self, event_id: int, fighter_id: int) -> dict[str, Any]:
        """MMA stats come from /event/{id}/team/{fighter_id}/statistics"""
        data = await self._api_get(f"/event/{event_id}/team/{fighter_id}/statistics")
        if not isinstance(data, dict):
            return {}
        return data.get("statistics") or {}

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────
    def _result(self, ev: dict, player_team_id: int | None) -> str:
        """Return 'win' / 'loss' / 'draw' / 'unknown' from player's perspective."""
        hs = ev.get("homeScore", {}).get("current")
        as_ = ev.get("awayScore", {}).get("current")
        if hs is None or as_ is None:
            return "unknown"
        try:
            hs, as_ = int(hs), int(as_)
        except Exception:
            return "unknown"
        is_home = ev.get("homeTeam", {}).get("id") == player_team_id
        if hs == as_:
            return "draw"
        if is_home:
            return "win" if hs > as_ else "loss"
        return "win" if as_ > hs else "loss"

    def _mma_result(self, ev: dict, fighter_id: int) -> str:
        """
        MMA win/loss from winnerCode:
          1 = homeTeam (fighter1) wins
          2 = awayTeam (fighter2) wins
          3 = draw / no contest
        """
        winner_code = ev.get("winnerCode")
        if winner_code is None:
            # Fallback: score-based
            return self._result(ev, fighter_id)
        is_home = ev.get("homeTeam", {}).get("id") == fighter_id
        if winner_code == 3:
            return "draw"
        if is_home:
            return "win" if winner_code == 1 else "loss"
        return "win" if winner_code == 2 else "loss"

    def _mma_method(self, ev: dict) -> str:
        """
        Fight finish method lives in the event, not in statistics.
        SofaScore stores it in:  ev.status.description  or  ev.finalResultOnly
        Examples: 'KO/TKO', 'Submission', 'Decision - Unanimous', 'Decision - Split'
        """
        # Try dedicated field first
        method = ev.get("finalResultOnly") or ev.get("winMethod") or ""
        if method:
            return str(method)
        # Fallback: status description often contains the method
        desc = ev.get("status", {}).get("description", "")
        for keyword in ("KO", "TKO", "Submission", "Decision", "No Contest", "DQ"):
            if keyword.lower() in desc.lower():
                return keyword
        return desc or "Unknown"

    def _meta(self, ev: dict) -> dict:
        home = ev.get("homeTeam", {}).get("name", "?")
        away = ev.get("awayTeam", {}).get("name", "?")
        hs   = ev.get("homeScore", {}).get("current", "-")
        as_  = ev.get("awayScore", {}).get("current", "-")
        return {
            "eventId":     ev.get("id"),
            "date":        ev.get("_eventDateIso", ""),
            "competition": ev.get("tournament", {}).get("name", "Unknown"),
            "homeTeam": home, "awayTeam": away,
            "score": f"{hs}-{as_}",
            "status": ev.get("status", {}).get("description", ""),
        }

    # ─────────────────────────────────────────────────────────────
    # 1. FOOTBALL aggregator
    # ─────────────────────────────────────────────────────────────
    def _aggregate_football(
        self, player_id: int, player_name: str,
        events: list[dict], stats_map: dict[int, dict]
    ) -> dict[str, Any]:

        summary: dict[str, Any] = {
            "playerId": player_id, "playerName": player_name,
            "sport": "football", "period": "last 7 days",
            # Counts
            "appearances": 0, "minutesPlayed": 0,
            "wins": 0, "losses": 0, "draws": 0,
            # Attacking
            "goals": 0, "assists": 0,
            "shots": 0, "shotsOnTarget": 0,
            "xG": 0.0, "xA": 0.0,
            "bigChancesCreated": 0,
            # Passing
            "keyPasses": 0, "totalPasses": 0, "accuratePasses": 0,
            "avgPassAccuracyPct": 0.0,
            # Dribbling
            "dribblesAttempted": 0, "dribblesSuccessful": 0,
            # Defending
            "tackles": 0, "interceptions": 0,
            "clearances": 0, "blockedShots": 0,
            # Duels
            "duelsWon": 0, "duelsTotal": 0, "aerialDuelsWon": 0,
            # Discipline
            "yellowCards": 0, "redCards": 0,
            # Goalkeeper / special
            "cleanSheets": 0,
            # Honours
            "hatTricks": 0,
            "manOfTheMatch": 0,
            # Injury (flagged in event data)
            "injuries": 0,
            # Rating
            "avgRating": 0.0,
            "matches": [],
        }

        ratings: list[float] = []
        pass_accs: list[float] = []

        for ev in events:
            eid   = ev.get("id")
            stats = stats_map.get(eid, {})

            # Injury flag — SofaScore marks it in event status
            status_code = ev.get("status", {}).get("type", "")
            if "injury" in str(ev.get("playerStatus", "")).lower():
                summary["injuries"] += 1

            if not stats:
                continue

            # Win / loss / draw
            # winnerCode: 1=home wins, 2=away wins, 3=draw
            # stats.teamId দিয়ে player এর team বের করি
            winner_code   = ev.get("winnerCode")
            stats_team_id = stats.get("teamId")
            home_id       = ev.get("homeTeam", {}).get("id")

            if winner_code == 3:
                result = "draw"
            elif winner_code in (1, 2):
                is_home = (stats_team_id == home_id) if stats_team_id else True
                result = ("win" if winner_code == 1 else "loss") if is_home else ("loss" if winner_code == 1 else "win")
            else:
                result = self._result(ev, stats_team_id or home_id)
            summary["wins"]   += result == "win"
            summary["losses"] += result == "loss"
            summary["draws"]  += result == "draw"

            g  = lambda k, d=0: stats.get(k, d)

            goals   = g("goals")
            minutes = g("minutesPlayed")
            rating  = round(g("rating", 0.0), 2)
            pass_ac = round(g("accuratePassesPercentage", 0.0), 1)

            summary["appearances"]      += 1
            summary["minutesPlayed"]    += minutes
            summary["goals"]            += goals
            summary["assists"]          += g("assists")
            summary["shots"]            += g("totalShots")
            summary["shotsOnTarget"]    += g("onTargetScoringAttempt")
            summary["xG"]               += round(g("expectedGoals",   0.0), 2)
            summary["xA"]               += round(g("expectedAssists", 0.0), 2)
            summary["bigChancesCreated"]+= g("bigChanceCreated")
            summary["keyPasses"]        += g("keyPass")
            summary["totalPasses"]      += g("totalPass")
            summary["accuratePasses"]   += g("accuratePasses")
            summary["dribblesAttempted"]+= g("attemptedDribbles")
            summary["dribblesSuccessful"]+= g("successfulDribbles")
            summary["tackles"]          += g("tackles")
            summary["interceptions"]    += g("interceptions")
            summary["clearances"]       += g("clearances")
            summary["blockedShots"]     += g("blockedShots")
            summary["duelsWon"]         += g("duelsWon")
            summary["duelsTotal"]       += g("totalDuels")
            summary["aerialDuelsWon"]   += g("aerialDuelsWon")
            summary["yellowCards"]      += g("yellowCards")
            summary["redCards"]         += g("redCards")
            summary["cleanSheets"]      += int(bool(g("cleanSheet", False)))
            summary["hatTricks"]        += int(goals >= 3)
            summary["manOfTheMatch"]    += int(bool(g("manOfTheMatch", False)))

            if rating > 0:
                ratings.append(rating)
            if pass_ac > 0:
                pass_accs.append(pass_ac)

            meta = self._meta(ev)
            summary["matches"].append({
                **meta, "result": result,
                "goals": goals, "assists": g("assists"),
                "xG": round(g("expectedGoals", 0.0), 2),
                "shots": g("totalShots"), "shotsOnTarget": g("onTargetScoringAttempt"),
                "keyPasses": g("keyPass"),
                "passAccuracyPct": pass_ac,
                "tackles": g("tackles"), "interceptions": g("interceptions"),
                "yellowCards": g("yellowCards"), "redCards": g("redCards"),
                "minutesPlayed": minutes, "rating": rating,
                "cleanSheet": bool(g("cleanSheet", False)),
                "hatTrick": goals >= 3,
                "manOfTheMatch": bool(g("manOfTheMatch", False)),
            })

        summary["xG"]  = round(summary["xG"], 2)
        summary["xA"]  = round(summary["xA"], 2)
        summary["avgRating"] = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
        summary["avgPassAccuracyPct"] = round(sum(pass_accs) / len(pass_accs), 1) if pass_accs else 0.0
        return summary

    # ─────────────────────────────────────────────────────────────
    # 2. BASKETBALL aggregator
    # ─────────────────────────────────────────────────────────────
    def _aggregate_basketball(
        self, player_id: int, player_name: str,
        events: list[dict], stats_map: dict[int, dict]
    ) -> dict[str, Any]:

        summary: dict[str, Any] = {
            "playerId": player_id, "playerName": player_name,
            "sport": "basketball", "period": "last 7 days",
            "games": 0,
            "wins": 0, "losses": 0, "draws": 0,
            # Scoring
            "totalPoints": 0, "pointsPerGame": 0.0,
            "fieldGoalsMade": 0, "fieldGoalsAttempted": 0,
            "threePointersMade": 0, "threePointersAttempted": 0,
            "freeThrowsMade": 0, "freeThrowsAttempted": 0,
            # Board & playmaking
            "totalRebounds": 0, "offensiveRebounds": 0, "defensiveRebounds": 0,
            "assists": 0,
            # Defence
            "blocks": 0, "steals": 0, "personalFouls": 0, "turnovers": 0,
            # Minutes
            "minutesPlayed": 0,
            # Honours
            "tripleDoubles": 0, "doubleDoubles": 0,
            "injuries": 0,
            "matches": [],
        }

        for ev in events:
            eid   = ev.get("id")
            stats = stats_map.get(eid, {})
            if not stats:
                continue

            result = self._result(ev, None)
            summary["wins"]   += result == "win"
            summary["losses"] += result == "loss"
            summary["draws"]  += result == "draw"

            g = lambda k, d=0: stats.get(k, d)

            points    = g("points") or g("scoredPoints") or 0
            rebounds  = g("rebounds") or g("totalRebounds") or 0
            assists   = g("assists") or 0
            blocks    = g("blocks") or 0
            steals    = g("steals") or 0
            off_reb   = g("offensiveRebounds") or 0
            def_reb   = g("defensiveRebounds") or 0
            fgm       = g("fieldGoalsMade") or g("twoPointersMade") or 0
            fga       = g("fieldGoalsAttempted") or g("twoPointersAttempted") or 0
            tpm       = g("threePointersMade") or 0
            tpa       = g("threePointersAttempted") or 0
            ftm       = g("freeThrowsMade") or 0
            fta       = g("freeThrowsAttempted") or 0
            minutes   = g("minutesPlayed") or 0
            fouls     = g("personalFouls") or g("fouls") or 0
            turnovers = g("turnovers") or 0

            # Triple-double: 10+ in 3 of: points, rebounds, assists, blocks, steals
            cats = [points, rebounds, assists, blocks, steals]
            double_digits = sum(1 for c in cats if c >= 10)
            triple_double = double_digits >= 3
            double_double = double_digits >= 2

            summary["games"]                  += 1
            summary["totalPoints"]            += points
            summary["fieldGoalsMade"]         += fgm
            summary["fieldGoalsAttempted"]    += fga
            summary["threePointersMade"]      += tpm
            summary["threePointersAttempted"] += tpa
            summary["freeThrowsMade"]         += ftm
            summary["freeThrowsAttempted"]    += fta
            summary["totalRebounds"]          += rebounds
            summary["offensiveRebounds"]      += off_reb
            summary["defensiveRebounds"]      += def_reb
            summary["assists"]                += assists
            summary["blocks"]                 += blocks
            summary["steals"]                 += steals
            summary["minutesPlayed"]          += minutes
            summary["personalFouls"]          += fouls
            summary["turnovers"]              += turnovers
            summary["tripleDoubles"]          += int(triple_double)
            summary["doubleDoubles"]          += int(double_double)

            meta = self._meta(ev)
            summary["matches"].append({
                **meta, "result": result,
                "points": points, "rebounds": rebounds, "assists": assists,
                "blocks": blocks, "steals": steals,
                "tripleDouble": triple_double, "doubleDouble": double_double,
                "minutesPlayed": minutes,
            })

        n = summary["games"]
        summary["pointsPerGame"]   = round(summary["totalPoints"] / n, 1) if n else 0.0
        summary["assistsPerGame"]  = round(summary["assists"] / n, 1) if n else 0.0
        summary["reboundsPerGame"] = round(summary["totalRebounds"] / n, 1) if n else 0.0
        return summary

    # ─────────────────────────────────────────────────────────────
    # 3. TENNIS aggregator
    # ─────────────────────────────────────────────────────────────
    def _aggregate_tennis(
        self, player_id: int, player_name: str,
        events: list[dict], stats_map: dict[int, dict]
    ) -> dict[str, Any]:

        GRAND_SLAMS = {"Australian Open", "Roland Garros", "Wimbledon", "US Open"}

        summary: dict[str, Any] = {
            "playerId": player_id, "playerName": player_name,
            "sport": "tennis", "period": "last 7 days",
            "matches": 0,
            "wins": 0, "losses": 0,
            # Serve
            "aces": 0, "doubleFaults": 0,
            "firstServePct": 0.0,
            "firstServeWonPct": 0.0,
            "secondServeWonPct": 0.0,
            "breakPointsFaced": 0, "breakPointsSaved": 0,
            # Return
            "breakPointsConverted": 0,
            # Sets
            "setsWon": 0, "setsLost": 0,
            "setBagels": 0,       # 6-0 sets won
            # Honours
            "grandSlamWins": 0,
            "injuries": 0,
            "matchesDetail": [],
        }

        first_serve_pcts: list[float] = []
        first_serve_won_pcts: list[float] = []

        for ev in events:
            eid   = ev.get("id")
            stats = stats_map.get(eid, {})
            if not stats:
                continue

            result = self._result(ev, None)
            summary["wins"]   += result == "win"
            summary["losses"] += result == "loss"
            summary["matches"] += 1

            g = lambda k, d=0: stats.get(k, d)

            aces         = g("aces") or g("numberOfAces") or 0
            double_faults= g("doubleFaults") or 0
            sets_won     = g("setsWon") or g("wonSets") or 0
            sets_lost    = g("setsLost") or g("lostSets") or 0
            bp_faced     = g("breakPointsFaced") or 0
            bp_saved     = g("breakPointsSaved") or 0
            bp_converted = g("breakPointsConverted") or 0
            fs_pct       = g("firstServePct") or g("firstServePercentage") or 0.0
            fs_won_pct   = g("firstServePointsWonPct") or g("firstServeWonPercentage") or 0.0

            # Bagel: a set won 6-0 — approximate via setsWon if detailed score absent
            bagels = g("setBagels") or 0
            if not bagels and sets_won > 0:
                # SofaScore sometimes returns period scores
                for period in ev.get("homeScore", {}).values():
                    if isinstance(period, dict):
                        for k, v in period.items():
                            if isinstance(v, int) and v == 6:
                                bagels += 1  # rough approximation

            # Grand Slam check via tournament name
            tournament_name = ev.get("tournament", {}).get("name", "")
            is_grand_slam_win = result == "win" and any(gs in tournament_name for gs in GRAND_SLAMS)

            summary["aces"]                += aces
            summary["doubleFaults"]        += double_faults
            summary["setsWon"]             += sets_won
            summary["setsLost"]            += sets_lost
            summary["breakPointsFaced"]    += bp_faced
            summary["breakPointsSaved"]    += bp_saved
            summary["breakPointsConverted"]+= bp_converted
            summary["setBagels"]           += bagels
            summary["grandSlamWins"]       += int(is_grand_slam_win)

            if fs_pct:
                first_serve_pcts.append(fs_pct)
            if fs_won_pct:
                first_serve_won_pcts.append(fs_won_pct)

            meta = self._meta(ev)
            summary["matchesDetail"].append({
                **meta, "result": result,
                "aces": aces, "doubleFaults": double_faults,
                "setsWon": sets_won, "setsLost": sets_lost,
                "setBagels": bagels, "grandSlamWin": is_grand_slam_win,
                "breakPointsSaved": bp_saved, "breakPointsConverted": bp_converted,
            })

        n = summary["matches"]
        summary["firstServePct"]    = round(sum(first_serve_pcts) / len(first_serve_pcts), 1) if first_serve_pcts else 0.0
        summary["firstServeWonPct"] = round(sum(first_serve_won_pcts) / len(first_serve_won_pcts), 1) if first_serve_won_pcts else 0.0
        summary["acesPerMatch"]     = round(summary["aces"] / n, 1) if n else 0.0
        return summary

    # ─────────────────────────────────────────────────────────────
    # 4. MMA / UFC aggregator
    # ─────────────────────────────────────────────────────────────
    def _aggregate_mma(
        self, fighter_id: int, fighter_name: str,
        events: list[dict], stats_map: dict[int, dict]
    ) -> dict[str, Any]:
        """
        Key differences from other sports:
        - Win/loss from winnerCode  (1=home wins, 2=away wins, 3=draw)
        - Fight method from event level (finalResultOnly / status.description)
        - Stats from /event/{id}/team/{fighter_id}/statistics
        - Stats keys: sigStrikesLanded, sigStrikesAttempted, knockdowns,
                      takedownsLanded, takedownsAttempted, submissionAttempts,
                      controlTimeSeconds, totalStrikesLanded
        """
        summary: dict[str, Any] = {
            "playerId": fighter_id, "playerName": fighter_name,
            "sport": "mma", "period": "last 7 days",
            "fights": 0,
            "winsKOTKO": 0, "winsSubmission": 0, "winsDecision": 0,
            "totalWins": 0, "losses": 0, "draws": 0,
            # Striking
            "significantStrikesLanded": 0, "significantStrikesAttempted": 0,
            "totalStrikesLanded": 0, "knockdowns": 0,
            # Grappling
            "takedownsLanded": 0, "takedownsAttempted": 0,
            "submissionAttempts": 0, "controlTimeSeconds": 0,
            # Time
            "totalFightTimeSeconds": 0,
            # Honours
            "fightOfTheNight": 0, "performanceOfTheNight": 0,
            "injuries": 0,
            "matches": [],
        }

        METHOD_KO  = {"ko", "tko", "ko/tko"}
        METHOD_SUB = {"submission", "sub"}

        for ev in events:
            eid    = ev.get("id")
            stats  = stats_map.get(eid, {})

            # ── Win / Loss — use winnerCode (not score) ──────────
            result = self._mma_result(ev, fighter_id)

            # ── Fight method — from event level ──────────────────
            method = self._mma_method(ev)
            method_lower = method.lower()

            summary["fights"] += 1
            if result == "win":
                summary["totalWins"] += 1
                if any(k in method_lower for k in METHOD_KO):
                    summary["winsKOTKO"]      += 1
                elif any(k in method_lower for k in METHOD_SUB):
                    summary["winsSubmission"] += 1
                else:
                    summary["winsDecision"]   += 1
            elif result == "loss":
                summary["losses"] += 1
            else:
                summary["draws"] += 1

            # ── Strike & grappling stats (from team stats endpoint) ──
            g = lambda k, d=0: stats.get(k, d)

            # SofaScore MMA stat keys (actual keys from API)
            sig_l  = g("sigStrikesLanded")      or g("significantStrikesLanded")      or 0
            sig_a  = g("sigStrikesAttempted")   or g("significantStrikesAttempted")   or 0
            tot_l  = g("totalStrikesLanded")    or 0
            kd     = g("knockdowns")            or 0
            td_l   = g("takedownsLanded")       or g("takedowns")                     or 0
            td_a   = g("takedownsAttempted")    or 0
            sub_a  = g("submissionAttempts")    or 0
            ctrl   = g("controlTimeSeconds")    or g("controlTime")                   or 0
            ft     = g("fightTimeSeconds")      or g("fightTime")                     or 0
            fotn   = bool(g("fightOfTheNight")  or g("bonusFightOfTheNight"))
            potn   = bool(g("performanceOfTheNight") or g("bonusPerformance"))

            summary["significantStrikesLanded"]    += sig_l
            summary["significantStrikesAttempted"] += sig_a
            summary["totalStrikesLanded"]          += tot_l
            summary["knockdowns"]                  += kd
            summary["takedownsLanded"]             += td_l
            summary["takedownsAttempted"]          += td_a
            summary["submissionAttempts"]          += sub_a
            summary["controlTimeSeconds"]          += ctrl
            summary["totalFightTimeSeconds"]       += ft
            summary["fightOfTheNight"]             += int(fotn)
            summary["performanceOfTheNight"]       += int(potn)

            meta = self._meta(ev)
            summary["matches"].append({
                **meta,
                "result": result,
                "method": method,
                "round": ev.get("roundInfo", {}).get("round"),
                "significantStrikesLanded": sig_l,
                "significantStrikesAttempted": sig_a,
                "knockdowns": kd,
                "takedownsLanded": td_l,
                "takedownsAttempted": td_a,
                "submissionAttempts": sub_a,
                "controlTimeSeconds": ctrl,
                "fightOfTheNight": fotn,
                "performanceOfTheNight": potn,
            })

        n = summary["fights"]
        if n:
            sig_den = max(summary["significantStrikesAttempted"], 1)
            summary["sigStrikeAccuracyPct"] = round(
                summary["significantStrikesLanded"] / sig_den * 100, 1)
            td_den  = max(summary["takedownsAttempted"], 1)
            summary["takedownAccuracyPct"]  = round(
                summary["takedownsLanded"] / td_den * 100, 1)
            summary["avgFightTimeSeconds"]  = round(
                summary["totalFightTimeSeconds"] / n, 0)
        return summary

    # ─────────────────────────────────────────────────────────────
    # Public entry-points (called by router)
    # ─────────────────────────────────────────────────────────────
    async def _build_summary(self, player_id: int, aggregator_fn) -> dict[str, Any]:
        player = await self.get_player_info(player_id)
        events = await self.get_recent_events(player_id)
        stats_map: dict[int, dict[str, Any]] = {}
        for ev in events:
            eid = ev.get("id")
            if eid:
                stats_map[eid] = await self.get_match_statistics(eid, player_id)
                await asyncio.sleep(0.2)
        name = player.get("playerName", "Unknown Player")
        return aggregator_fn(player_id, name, events, stats_map)

    async def get_football_summary(self, player_id: int) -> dict[str, Any]:
        return await self._build_summary(player_id, self._aggregate_football)

    async def get_basketball_summary(self, player_id: int) -> dict[str, Any]:
        return await self._build_summary(player_id, self._aggregate_basketball)

    async def get_tennis_summary(self, player_id: int) -> dict[str, Any]:
        return await self._build_summary(player_id, self._aggregate_tennis)

    async def get_mma_summary(self, fighter_id: int) -> dict[str, Any]:
        """
        MMA fighters are stored as 'teams' in SofaScore.
        Uses /team/{id}/events and /event/{id}/team/{id}/statistics
        """
        # Fighter info from team endpoint
        fighter = await self.get_fighter_info(fighter_id)
        name    = fighter.get("playerName", "Unknown Fighter")

        # Events from team endpoint (not player endpoint)
        events  = await self.get_recent_mma_events(fighter_id)

        # Stats from team stats endpoint
        stats_map: dict[int, dict[str, Any]] = {}
        for ev in events:
            eid = ev.get("id")
            if eid:
                stats_map[eid] = await self.get_mma_fight_statistics(eid, fighter_id)
                await asyncio.sleep(0.2)

        return self._aggregate_mma(fighter_id, name, events, stats_map)