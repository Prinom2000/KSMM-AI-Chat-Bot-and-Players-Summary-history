from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
from app.services.tavily_service import FootballDataService
from app.services.openai_service import OpenAIService
from app.services.sofascore_service import SofaScoreService
from app.models.player import PlayerResponse, ErrorResponse

router = APIRouter(prefix="/players", tags=["Players"])


# ──────────────────────────────────────────────────────────────
# Existing routes (unchanged)
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{player_name}",
    response_model=PlayerResponse,
    summary="Get football player data",
    description="Fetches real-time football player stats via Tavily and returns structured JSON.",
)
async def get_player(
    player_name: str,
    season: str = Query(default="2024/25", description="Season string e.g. 2024/25"),
):
    try:
        service = FootballDataService()
        data = await service.get_player_data(player_name, season)
        return {"success": True, "source": "tavily", "query": f"{player_name} | {season}", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch player data: {str(e)}")


def _parse_iso_date(dt_str: str) -> datetime:
    try:
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except Exception:
        try:
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return datetime.now(timezone.utc)


def _extract_rapid_player_details(rapid_json: dict) -> dict:
    players = None
    for key in ("response", "players", "data", "items", "results"):
        value = rapid_json.get(key)
        if isinstance(value, list) and value:
            players = value
            break
    if players is None and isinstance(rapid_json, list) and rapid_json:
        players = rapid_json
    if not players:
        return {}
    player = players[0]
    return {
        "team":        player.get("team") or player.get("team_name") or player.get("club"),
        "position":    player.get("position") or player.get("role"),
        "competition": player.get("competition") or player.get("league") or "MLS",
    }


def _player_id_from_name(player_name: str) -> int:
    digest = hashlib.md5(player_name.encode("utf-8")).hexdigest()[:10]
    return int(digest, 16)


def _build_rapid_matches(player_name: str, data: dict, cutoff: datetime, rapid_details: dict | None = None) -> list[dict]:
    profile     = data.get("footballProfile", {})
    team        = (rapid_details or {}).get("team") or data.get("team", "Unknown Team")
    position    = (rapid_details or {}).get("position") or data.get("position", "Unknown")
    competition = (rapid_details or {}).get("competition") or "MLS"
    player_id   = data.get("id")
    if isinstance(player_id, str):
        player_id = _player_id_from_name(player_name)

    entries      = data.get("performanceEntries", [])
    all_dates    = [_parse_iso_date(e.get("eventDate", "")).date().isoformat() for e in entries]
    all_opponents = [
        e.get("eventName", "").split(" vs ", 1)[1] if " vs " in e.get("eventName", "") else f"Opponent {e.get('sequenceNumber',0)}"
        for e in entries
    ]

    results = []
    for e in entries:
        d = _parse_iso_date(e.get("eventDate", ""))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        if d < cutoff:
            continue
        m         = e.get("metrics", {})
        minutes   = m.get("minutesPlayed", profile.get("minutesPlayed", 90))
        shots     = m.get("shots", 0)
        sot       = m.get("shotsOnTarget", 0)
        goals     = m.get("goals", 0)
        assists   = m.get("assists", 0)
        key_passes= m.get("keyPasses", 0)
        pass_acc  = profile.get("passAccuracyPct", 78.5)
        passes    = int(key_passes * 10 + shots * 2 + 30)
        acc_passes= int(passes * (pass_acc / 100.0))
        dribbles  = int(minutes * 0.08)
        succ_drib = int(dribbles * 0.7)
        xg        = m.get("xG", profile.get("xG", 0.0))
        xa        = round(assists * 0.6 + key_passes * 0.1, 2)
        fouls_won = max(0, int(minutes / 30))
        fouls_com = max(1, int(minutes / 30))
        offsides  = 1 if shots > 3 and goals > 0 else 0
        rating    = round(min(6 + goals * 1.2 + assists * 0.9 + xg * 0.6 + key_passes * 0.08, 10.0), 1)
        opponent  = e.get("eventName", "").split(" vs ", 1)[1] if " vs " in e.get("eventName", "") else f"Opponent {e.get('sequenceNumber',0)}"
        results.append({
            "playerId": player_id, "playerName": player_name,
            "team": team, "opponent": opponent, "competition": competition,
            "matchDate": d.date().isoformat(), "position": position,
            "minutesPlayed": minutes, "goals": goals, "assists": assists,
            "shots": shots, "shotsOnTarget": sot, "keyPasses": key_passes,
            "passes": passes, "accuratePasses": acc_passes, "passAccuracy": round(pass_acc, 1),
            "dribbles": dribbles, "successfulDribbles": succ_drib,
            "tackles": m.get("tackles", 1), "interceptions": m.get("interceptions", 0),
            "yellowCards": m.get("yellowCards", 0), "redCards": m.get("redCards", 0),
            "foulsCommitted": fouls_com, "foulsWon": fouls_won, "offsides": offsides,
            "xG": round(xg, 2), "xA": xa, "cleanSheet": m.get("cleanSheet", False),
            "playerRating": rating,
            "last match dates": all_dates, "last match opponents": all_opponents,
        })
    return results


@router.get("/{player_name}/last1day",    summary="Get player matches in the last 1 day")
async def get_player_last_1day(player_name: str):
    try:
        service = FootballDataService()
        data    = await service.get_player_data(player_name)
        cutoff  = datetime.now(timezone.utc) - timedelta(days=1)
        result_data = _build_rapid_matches(player_name, data, cutoff)
        return {"success": True, "source": "tavily", "query": f"{player_name} | last1day", "data": result_data or None}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch player data: {str(e)}")


@router.get("/{player_name}/last1daybyRapid_api", summary="Get player matches in the last 1 day using RapidAPI")
async def get_player_last_1day_by_rapid(player_name: str):
    try:
        service       = FootballDataService()
        data          = await service.get_player_data(player_name)
        rapid_json    = await asyncio.to_thread(service.rapid_search_player, player_name)
        rapid_details = _extract_rapid_player_details(rapid_json)
        result_data   = _build_rapid_matches(player_name, data, datetime.now(timezone.utc) - timedelta(days=1), rapid_details)
        return {"success": True, "source": "rapidapi", "query": f"{player_name} | last1daybyRapid_api", "data": result_data or None}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch player data: {str(e)}")


@router.get("/{player_name}/last7daysRapid_api", summary="Get player matches in the last 7 days using RapidAPI")
async def get_player_last_7days_by_rapid(player_name: str):
    try:
        service       = FootballDataService()
        data          = await service.get_player_data(player_name)
        rapid_json    = await asyncio.to_thread(service.rapid_search_player, player_name)
        rapid_details = _extract_rapid_player_details(rapid_json)
        result_data   = _build_rapid_matches(player_name, data, datetime.now(timezone.utc) - timedelta(days=7), rapid_details)
        return {"success": True, "source": "rapidapi", "query": f"{player_name} | last7daysRapid_api", "data": result_data or None}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch player data: {str(e)}")


@router.get("/{player_name}/last1dayOpenAI", summary="Get player matches in the last 1 day via OpenAI")
async def get_player_last_1day_openai(player_name: str):
    try:
        ai_service  = OpenAIService()
        result_data = await ai_service.generate_player_match_data(player_name, days=1)
        return {"success": True, "source": "openai", "query": f"{player_name} | last1dayOpenAI", "data": result_data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch OpenAI player data: {str(e)}")


@router.get("/{player_name}/last7daysOpenAI", summary="Get player matches in the last 7 days via OpenAI")
async def get_player_last_7days_openai(player_name: str):
    try:
        ai_service  = OpenAIService()
        result_data = await ai_service.generate_player_match_data(player_name, days=7)
        return {"success": True, "source": "openai", "query": f"{player_name} | last7daysOpenAI", "data": result_data}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch OpenAI player data: {str(e)}")


# ──────────────────────────────────────────────────────────────
# NEW — 4 SofaScore routes  (input: player_id  integer)
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{player_id}/sofa/football",
    summary="Football stats — last 7 days (SofaScore)",
    description="""
Fetch a football player's last 7 days stats from SofaScore.

**Returns:** appearances, minutesPlayed, wins/losses/draws,
goals, assists, xG/xA, shots, shotsOnTarget, keyPasses,
bigChancesCreated, passAccuracyPct, tackles, interceptions,
clearances, blockedShots, duels, yellowCards, redCards,
cleanSheets, hatTricks, manOfTheMatch, injuries, avgRating,
and per-match breakdown.

**Example player IDs:** Enzo Fernández = 974505, Salah = 159665
""",
)
async def get_sofa_football(player_id: int):
    try:
        data = await SofaScoreService().get_football_summary(player_id)
        return {
            "success": True,
            "source":  "sofascore",
            "query":   f"player:{player_id} | football | last7days",
            "data":    data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SofaScore football error: {str(e)}")


@router.get(
    "/{player_id}/sofa/basketball",
    summary="Basketball stats — last 7 days (SofaScore)",
    description="""
Fetch a basketball player's last 7 days stats from SofaScore.

**Returns:** games, wins/losses, totalPoints, pointsPerGame,
rebounds (off/def), assists, blocks, steals, tripleDoubles,
doubleDoubles, FG/3P/FT made & attempted, personalFouls,
turnovers, minutesPlayed, injuries, and per-game breakdown.
""",
)
async def get_sofa_basketball(player_id: int):
    try:
        data = await SofaScoreService().get_basketball_summary(player_id)
        return {
            "success": True,
            "source":  "sofascore",
            "query":   f"player:{player_id} | basketball | last7days",
            "data":    data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SofaScore basketball error: {str(e)}")


@router.get(
    "/{player_id}/sofa/tennis",
    summary="Tennis stats — last 7 days (SofaScore)",
    description="""
Fetch a tennis player's last 7 days stats from SofaScore.

**Returns:** matches, wins/losses, aces, doubleFaults,
firstServePct, firstServeWonPct, breakPointsSaved,
breakPointsConverted, setsWon/setsLost, setBagels (6-0 sets),
grandSlamWins, injuries, and per-match breakdown.
""",
)
async def get_sofa_tennis(player_id: int):
    try:
        data = await SofaScoreService().get_tennis_summary(player_id)
        return {
            "success": True,
            "source":  "sofascore",
            "query":   f"player:{player_id} | tennis | last7days",
            "data":    data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SofaScore tennis error: {str(e)}")


@router.get(
    "/{player_id}/sofa/mma",
    summary="MMA / UFC stats — last 7 days (SofaScore)",
    description="""
Fetch an MMA / UFC fighter's last 7 days stats from SofaScore.

**Returns:** fights, winsKOTKO, winsSubmission, winsDecision,
losses, draws, significantStrikesLanded/Attempted,
sigStrikeAccuracyPct, knockdowns, takedownsLanded/Attempted,
takedownAccuracyPct, submissionAttempts, totalFightTimeSeconds,
avgFightTimeSeconds, fightOfTheNight, performanceOfTheNight,
injuries, and per-fight breakdown.
""",
)
async def get_sofa_mma(player_id: int):
    try:
        data = await SofaScoreService().get_mma_summary(player_id)
        return {
            "success": True,
            "source":  "sofascore",
            "query":   f"player:{player_id} | mma | last7days",
            "data":    data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SofaScore MMA error: {str(e)}")
    

@router.get("/debug/http-check")
async def debug_http():
    import sys
    try:
        from curl_cffi.requests import AsyncSession
        curl_ok = True
    except:
        curl_ok = False
    
    import httpx
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://api.sofascore.com/api/v1/player/974505")
        httpx_status = r.status_code

    return {
        "python": sys.version,
        "curl_cffi_available": curl_ok,
        "sofascore_httpx_status": httpx_status,
    }