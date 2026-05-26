# ⚽ Football Player Data API

Real-time football player statistics fetched via **Tavily Search**, returned as structured JSON.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Key
Edit `.env` and add your Tavily and RapidAPI keys:
```env
TAVILY_API_KEY=your_tavily_api_key_here
RAPIDAPI_KEY=your_rapidapi_key_here
```
Get your free Tavily key at: https://app.tavily.com
Get your RapidAPI key at: https://rapidapi.com

### 3. Run the server
```bash
python run.py
```
Or:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/players/{player_name}` | Get player data |
| GET | `/players/{player_name}/last1daybyRapid_api` | Get last 1 day matches via RapidAPI |
| GET | `/players/{player_name}/last7daysRapid_api` | Get last 7 days matches via RapidAPI |
| GET | `/players/{player_name}/last1dayOpenAI` | Get last 1 day matches via OpenAI |
| GET | `/players/{player_name}/last7daysOpenAI` | Get last 7 days matches via OpenAI |

## Example Request

```bash
curl "http://localhost:8000/players/Erling%20Haaland?season=2024/25"
curl "http://localhost:8000/players/Mohamed%20Salah"
curl "http://localhost:8000/players/Kylian%20Mbappe"
```

## Response Structure

```json
{
  "success": true,
  "source": "tavily",
  "query": "Erling Haaland | 2024/25",
  "data": {
    "id": "...",
    "name": "Erling Haaland",
    "position": "Forward",
    "nationality": "Norway",
    "dateOfBirth": "2000-07-21",
    "teamId": "...",
    "sport": "FOOTBALL",
    "footballProfile": { ... },
    "performanceEntries": [ ... ],
    "statTimeline": [ ... ]
  }
}
```

## Project Structure

```
football-api/
├── app/
│   ├── main.py              # FastAPI app
│   ├── routers/
│   │   └── players.py       # Player routes
│   ├── models/
│   │   └── player.py        # Pydantic models
│   └── services/
│       └── tavily_service.py # Tavily data fetcher & parser
├── .env                     # API keys (never commit!)
├── requirements.txt
├── run.py
└── README.md
```
