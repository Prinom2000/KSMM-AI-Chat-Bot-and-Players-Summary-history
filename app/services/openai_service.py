import os
import re
import json
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class OpenAIService:
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in .env file")
        self.api_key = OPENAI_API_KEY

    async def generate_player_match_data(self, player_name: str, days: int) -> list[dict]:
        today = datetime.now(timezone.utc).date().isoformat()
        window = "last 1 day" if days == 1 else "last 7 days"
        match_count = 1 if days == 1 else 3

        prompt = (
            f"You are a football statistics JSON generator. Generate only valid JSON array output. "
            f"Create {match_count} match records for player '{player_name}' within the {window} relative to UTC date {today}. "
            "Each record must include exactly these fields: playerId, playerName, team, opponent, competition, matchDate, "
            "position, minutesPlayed, goals, assists, shots, shotsOnTarget, keyPasses, passes, accuratePasses, passAccuracy, "
            "dribbles, successfulDribbles, tackles, interceptions, yellowCards, redCards, foulsCommitted, foulsWon, offsides, xG, xA, cleanSheet, playerRating. "
            "matchDate must be formatted as YYYY-MM-DD. playerRating must be a number between 1.0 and 10.0. Use realistic football match values. "
            "Do not add any explanatory text, markdown fences, or extra content. Output only a JSON array."
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a JSON generator that outputs only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 700,
                },
            )

        if response.status_code != 200:
            raise ValueError(f"OpenAI request failed: {response.status_code} {response.text}")

        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_json_output(content)

    def _parse_json_output(self, text: str) -> list[dict]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"```$", "", cleaned, flags=re.IGNORECASE).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"(\[.*\])", cleaned, flags=re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise ValueError("OpenAI output could not be parsed as JSON")
