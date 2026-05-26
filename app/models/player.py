from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ─── Football Profile ───────────────────────────────────────────────────────

class FootballProfile(BaseModel):
    id: str
    playerId: str
    season: str
    goals: int
    assists: int
    shots: int
    shotsOnTarget: int
    xG: float
    cleanSheets: int
    tackles: int
    interceptions: int
    clearances: int
    yellowCards: int
    redCards: int
    wins: int
    draws: int
    losses: int
    passAccuracyPct: float
    keyPasses: int
    appearances: int
    minutesPlayed: int


# ─── Performance Entry ───────────────────────────────────────────────────────

class PerformanceMetrics(BaseModel):
    goals: int
    assists: int
    minutesPlayed: int
    yellowCards: int
    shots: int
    shotsOnTarget: int
    keyPasses: int
    cleanSheet: bool
    xG: float


class PerformanceEntry(BaseModel):
    id: str
    playerId: str
    sequenceNumber: int
    season: str
    eventName: str
    eventDate: str
    sport: str
    win: bool
    draw: bool
    metrics: PerformanceMetrics


# ─── Stat Timeline ───────────────────────────────────────────────────────────

class CumulativeStats(BaseModel):
    goals: int
    assists: int
    cleanSheets: int
    wins: int
    draws: int
    losses: int
    yellowCards: int
    shots: int
    shotsOnTarget: int
    minutesPlayed: int


class DeltaStats(BaseModel):
    goals: int
    assists: int
    yellowCards: int
    shots: int
    keyPasses: int


class StatTimeline(BaseModel):
    id: str
    playerId: str
    performanceEntryId: str
    season: str
    sequenceNumber: int
    eventLabel: str
    eventDate: str
    sport: str
    cumulativeStats: CumulativeStats
    deltaStats: DeltaStats


# ─── Player (root) ───────────────────────────────────────────────────────────

class Player(BaseModel):
    id: str
    name: str
    position: str
    nationality: str
    dateOfBirth: str
    teamId: str
    sport: str
    footballProfile: FootballProfile
    performanceEntries: List[PerformanceEntry]
    statTimeline: List[StatTimeline]


# ─── API Response Wrapper ─────────────────────────────────────────────────────

class PlayerResponse(BaseModel):
    success: bool
    source: str
    query: str
    data: Player


class ErrorResponse(BaseModel):
    success: bool
    error: str
    detail: Optional[str] = None
