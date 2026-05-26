import os
import re
import json
import hashlib
import http.client
from urllib.parse import quote_plus
import httpx
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")


def _uid(seed: str) -> str:
    """Generate a deterministic 24-char hex id from a seed string."""
    return hashlib.md5(seed.encode()).hexdigest()[:24]


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _extract_number(text: str, pattern: str, default=0):
    """Extract the first number after a regex pattern in text."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        num_str = re.search(r"[\d.]+", text[match.end():match.end()+20])
        if num_str:
            return num_str.group()
    return default


class FootballDataService:
    def __init__(self):
        if not TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY is not set in .env file")
        self.client = TavilyClient(api_key=TAVILY_API_KEY)

    def _search(self, query: str, max_results: int = 5) -> list[dict]:
        """Perform a Tavily search and return results."""
        response = self.client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
        )
        return response

    def rapid_search_player(self, player_name: str) -> dict:
        """Perform a RapidAPI football player search using the RapidAPI key from .env."""
        if not RAPIDAPI_KEY:
            raise ValueError("RAPIDAPI_KEY is not set in .env file")

        conn = http.client.HTTPSConnection("free-api-live-football-data.p.rapidapi.com")
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "free-api-live-football-data.p.rapidapi.com",
            "Content-Type": "application/json",
        }
        path = f"/football-players-search?search={quote_plus(player_name)}"
        conn.request("GET", path, headers=headers)
        res = conn.getresponse()
        raw = res.read()
        conn.close()

        text = raw.decode("utf-8")
        if res.status != 200:
            raise ValueError(f"RapidAPI request failed: {res.status} {text}")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise ValueError("Failed to parse RapidAPI JSON response")

    def _parse_stats_from_results(self, results: dict, player_name: str, season: str) -> dict:
        """Parse raw stats from Tavily search results."""
        # Combine all content for parsing
        all_content = ""
        if results.get("answer"):
            all_content += results["answer"] + "\n"
        for r in results.get("results", []):
            all_content += r.get("content", "") + "\n"

        # Try to extract common stats via regex patterns
        def find_stat(patterns, as_float=False, default=0):
            for pattern in patterns:
                match = re.search(pattern, all_content, re.IGNORECASE)
                if match:
                    try:
                        val = match.group(1).replace(",", "")
                        return float(val) if as_float else int(float(val))
                    except Exception:
                        continue
            return default

        goals = find_stat([
            rf"{player_name}.*?(\d+)\s*goals?",
            r"(\d+)\s*goals?\s*(?:and|,|\s)",
            r"goals?[:\s]+(\d+)",
        ])
        assists = find_stat([
            rf"{player_name}.*?(\d+)\s*assists?",
            r"(\d+)\s*assists?",
            r"assists?[:\s]+(\d+)",
        ])
        appearances = find_stat([
            r"(\d+)\s*(?:appearances?|games?|matches?)",
            r"appearances?[:\s]+(\d+)",
        ]) or 1
        shots = find_stat([r"(\d+)\s*shots?", r"shots?[:\s]+(\d+)"])
        shots_on_target = find_stat([r"(\d+)\s*shots?\s*on\s*target", r"on\s*target[:\s]+(\d+)"])
        yellow_cards = find_stat([r"(\d+)\s*yellow\s*cards?", r"yellow[:\s]+(\d+)"])
        red_cards = find_stat([r"(\d+)\s*red\s*cards?", r"red[:\s]+(\d+)"])
        assists = max(assists, 0)

        # Derived / estimated stats
        minutes_played = appearances * 85
        wins = max(int(appearances * 0.55), 1)
        draws = max(int(appearances * 0.15), 0)
        losses = max(appearances - wins - draws, 0)
        xg = round(goals * 0.88 + shots * 0.05, 2)
        pass_accuracy = 78.5
        key_passes = max(int(assists * 2.5 + goals * 0.3), 0)
        tackles = max(int(appearances * 0.4), 0)
        interceptions = max(int(appearances * 0.2), 0)
        clearances = max(int(appearances * 0.3), 0)

        return {
            "goals": goals,
            "assists": assists,
            "appearances": appearances,
            "shots": shots or max(goals * 4, 1),
            "shotsOnTarget": shots_on_target or max(goals * 2, 1),
            "yellowCards": yellow_cards,
            "redCards": red_cards,
            "minutesPlayed": minutes_played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "xG": xg,
            "passAccuracyPct": pass_accuracy,
            "keyPasses": key_passes,
            "cleanSheets": 0,
            "tackles": tackles,
            "interceptions": interceptions,
            "clearances": clearances,
        }

    def _parse_player_bio(self, results: dict, player_name: str) -> dict:
        """Extract bio info (position, nationality, DOB, team)."""
        all_content = ""
        if results.get("answer"):
            all_content += results["answer"] + "\n"
        for r in results.get("results", []):
            all_content += r.get("content", "") + "\n"

        def find(patterns, default="Unknown"):
            for p in patterns:
                m = re.search(p, all_content, re.IGNORECASE)
                if m:
                    return m.group(1).strip()
            return default

        position = find([
            r"plays?\s+as\s+(?:a|an)?\s*([\w\s]+?)(?:\s+for|\s+at|\.|,)",
            r"position[:\s]+([\w\s]+?)(?:\.|,|\n)",
            r"(striker|forward|midfielder|defender|goalkeeper|winger|centre.back|full.back)",
        ], "Forward")

        nationality = find([
            r"(Norwegian|English|French|Spanish|German|Brazilian|Argentine|Portuguese|Dutch|Belgian)",
            r"nationality[:\s]+([\w]+)",
        ], "Unknown")

        dob = find([
            r"born\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4})",
            r"born[:\s]+(\w+\s+\d{1,2},?\s+\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ], "1990-01-01")

        team = find([
            r"(?:plays?|playing)\s+for\s+([\w\s]+?)(?:\s+in|\s+at|\.|,)",
            r"current\s+club[:\s]+([\w\s]+?)(?:\.|,|\n)",
            r"(?:at|for)\s+([\w\s]+?)\s+(?:FC|City|United|Athletic|Club)",
        ], "Unknown Club")

        # Normalize position
        pos_lower = position.lower()
        if any(w in pos_lower for w in ["striker", "forward", "attacker"]):
            position = "Forward"
        elif "mid" in pos_lower:
            position = "Midfielder"
        elif any(w in pos_lower for w in ["defender", "back", "centre-back"]):
            position = "Defender"
        elif "goal" in pos_lower or "keeper" in pos_lower:
            position = "Goalkeeper"
        else:
            position = position.title()

        # Normalize nationality
        nat_map = {
            "Norwegian": "Norway", "English": "England", "French": "France",
            "Spanish": "Spain", "German": "Germany", "Brazilian": "Brazil",
            "Argentine": "Argentina", "Portuguese": "Portugal",
            "Dutch": "Netherlands", "Belgian": "Belgium",
        }
        nationality = nat_map.get(nationality, nationality)

        return {
            "position": position,
            "nationality": nationality,
            "dateOfBirth": dob,
            "team": team,
        }

    def _build_performance_entries(self, player_id: str, stats: dict, season: str, player_name: str) -> tuple[list, list]:
        """Build synthetic but realistic performance entries and timelines from season totals."""
        appearances = max(stats["appearances"], 1)
        goals = stats["goals"]
        assists = stats["assists"]

        entries = []
        timelines = []

        cum_goals = 0
        cum_assists = 0
        cum_shots = 0
        cum_sot = 0
        cum_minutes = 0
        cum_wins = 0
        cum_draws = 0
        cum_losses = 0
        cum_yellow = 0

        goals_per_game = goals / appearances
        assists_per_game = assists / appearances

        for i in range(min(appearances, 10)):  # cap at 10 entries
            seq = i + 1
            perf_id = f"perf_{seq:03d}"
            timeline_id = f"timeline_{seq:03d}"

            g = 2 if i == 0 else (1 if i % 3 == 1 else 0)
            a = 1 if i % 4 == 1 else 0
            shots_g = 5 if g >= 2 else (3 if g == 1 else 2)
            sot_g = shots_g - 1
            mins = 90 if i < appearances - 1 else 78
            yellow = 1 if i == 1 else 0
            result_roll = i % 5
            win = result_roll not in (2, 4)
            draw = result_roll == 2
            xg_g = round(g * 0.9 + shots_g * 0.05, 2)

            # Keep totals capped near real totals
            if cum_goals + g > goals:
                g = max(goals - cum_goals, 0)
            if cum_assists + a > assists:
                a = max(assists - cum_assists, 0)

            cum_goals += g
            cum_assists += a
            cum_shots += shots_g
            cum_sot += sot_g
            cum_minutes += mins
            cum_yellow += yellow
            if win:
                cum_wins += 1
            elif draw:
                cum_draws += 1
            else:
                cum_losses += 1

            now = datetime.now(timezone.utc)
            days_back = min(appearances, 10) - seq
            event_date_dt = now - timedelta(days=days_back)
            event_date = event_date_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            entry = {
                "id": perf_id,
                "playerId": player_id,
                "sequenceNumber": seq,
                "season": season,
                "eventName": f"Match {seq} vs Opponent {seq} ({season})",
                "eventDate": event_date,
                "sport": "FOOTBALL",
                "win": win,
                "draw": draw,
                "metrics": {
                    "goals": g,
                    "assists": a,
                    "minutesPlayed": mins,
                    "yellowCards": yellow,
                    "shots": shots_g,
                    "shotsOnTarget": sot_g,
                    "keyPasses": a + (1 if g > 0 else 0),
                    "cleanSheet": False,
                    "xG": xg_g,
                },
            }

            timeline = {
                "id": timeline_id,
                "playerId": player_id,
                "performanceEntryId": perf_id,
                "season": season,
                "sequenceNumber": seq,
                "eventLabel": f"G{seq}",
                "eventDate": event_date,
                "sport": "FOOTBALL",
                "cumulativeStats": {
                    "goals": cum_goals,
                    "assists": cum_assists,
                    "cleanSheets": 0,
                    "wins": cum_wins,
                    "draws": cum_draws,
                    "losses": cum_losses,
                    "yellowCards": cum_yellow,
                    "shots": cum_shots,
                    "shotsOnTarget": cum_sot,
                    "minutesPlayed": cum_minutes,
                },
                "deltaStats": {
                    "goals": g,
                    "assists": a,
                    "yellowCards": yellow,
                    "shots": shots_g,
                    "keyPasses": a + (1 if g > 0 else 0),
                },
            }

            entries.append(entry)
            timelines.append(timeline)

        return entries, timelines

    async def get_player_data(self, player_name: str, season: str = "2024/25") -> dict:
        """Main method: fetch and assemble full player JSON."""
        # Search 1: bio
        bio_results = self._search(f"{player_name} footballer position nationality date of birth current club")
        bio = self._parse_player_bio(bio_results, player_name)

        # Search 2: season stats
        stats_results = self._search(
            f"{player_name} {season} season goals assists appearances stats football"
        )
        stats = self._parse_stats_from_results(stats_results, player_name, season)

        # IDs
        player_id = _uid(player_name)
        team_id = _uid(bio["team"])
        profile_id = _uid(player_name + "_profile")

        performance_entries, stat_timeline = self._build_performance_entries(
            player_id, stats, season, player_name
        )

        return {
            "id": player_id,
            "name": player_name,
            "position": bio["position"],
            "nationality": bio["nationality"],
            "dateOfBirth": bio["dateOfBirth"],
            "team": bio["team"],
            "teamId": team_id,
            "sport": "FOOTBALL",
            "footballProfile": {
                "id": profile_id,
                "playerId": player_id,
                "season": season,
                "goals": stats["goals"],
                "assists": stats["assists"],
                "shots": stats["shots"],
                "shotsOnTarget": stats["shotsOnTarget"],
                "xG": stats["xG"],
                "cleanSheets": stats["cleanSheets"],
                "tackles": stats["tackles"],
                "interceptions": stats["interceptions"],
                "clearances": stats["clearances"],
                "yellowCards": stats["yellowCards"],
                "redCards": stats["redCards"],
                "wins": stats["wins"],
                "draws": stats["draws"],
                "losses": stats["losses"],
                "passAccuracyPct": stats["passAccuracyPct"],
                "keyPasses": stats["keyPasses"],
                "appearances": stats["appearances"],
                "minutesPlayed": stats["minutesPlayed"],
            },
            "performanceEntries": performance_entries,
            "statTimeline": stat_timeline,
        }
