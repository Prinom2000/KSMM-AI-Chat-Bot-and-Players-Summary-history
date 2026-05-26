from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import players

app = FastAPI(
    title="Football Player Data API",
    description="Real-time football player statistics via Tavily search",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "message": "Football Player API is running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}
