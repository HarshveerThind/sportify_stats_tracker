"""
Core tables for Spotify stats tracker using SQLAlchemy Core v2.
All timestamps are timezone-aware in UTC for portability.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    MetaData, Table, Column, String, Text, Integer, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint, create_engine
)
from sqlalchemy.engine import Engine
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///stats.db")

# Single metadata and engine for the app
metadata = MetaData()

# Helper to get "now" in UTC
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

# user_info table
user_info = Table(
    "user_info",
    metadata,
    Column("user_id", String, primary_key=True),  # Spotify user id
    Column("display_name", String, nullable=True),
    Column("email", String, nullable=True),
    Column("profile_image", Text, nullable=True),
    Column("country", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()),
    Column("refresh_token", Text, nullable=False),
    Column("last_recent_cursor", DateTime(timezone=True), nullable=True),
)

# artists table
artists = Table(
    "artists",
    metadata,
    Column("artist_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("genres", Text, nullable=True),  # keep null for now or store JSON text later
)

# tracks table
tracks = Table(
    "tracks",
    metadata,
    Column("track_id", String, primary_key=True),
    Column("artist_id", String, ForeignKey("artists.artist_id"), nullable=False),
    Column("title", String, nullable=False),
    Column("album_name", String, nullable=True),
    Column("duration_ms", Integer, nullable=False),

    # optional audio features columns for future
    Column("danceability", Integer, nullable=True),   # keep numeric columns ready but unused
    Column("energy", Integer, nullable=True),
    Column("tempo", Integer, nullable=True),
    Column("valence", Integer, nullable=True),
    Column("loudness", Integer, nullable=True),
    Column("acousticness", Integer, nullable=True),
)

# plays table
plays = Table(
    "plays",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("user_info.user_id"), nullable=False),
    Column("track_id", String, ForeignKey("tracks.track_id"), nullable=False),
    Column("played_at", DateTime(timezone=True), nullable=False),
    Column("elapsed_ms", Integer, nullable=True),
    Column("is_skip", Boolean, nullable=True),
    UniqueConstraint("user_id", "played_at", name="uq_user_played_at"),
    Index("ix_user_played_at", "user_id", "played_at"),
    Index("ix_user_track", "user_id", "track_id"),
)

# daily_totals table
# Store day as UTC midnight DateTime for "timezone-aware everywhere"
daily_totals = Table(
    "daily_totals",
    metadata,
    Column("user_id", String, ForeignKey("user_info.user_id"), primary_key=True),
    Column("day", DateTime(timezone=True), primary_key=True),  # UTC midnight for the day
    Column("minutes_listened", Integer, nullable=False, default=0),
    Column("top_track_id", String, ForeignKey("tracks.track_id"), nullable=True),
    Column("top_artist_id", String, ForeignKey("artists.artist_id"), nullable=True),
    Column("repeats", Integer, nullable=False, default=0),
    Column("skips", Integer, nullable=False, default=0),
)

_engine: Optional[Engine] = None

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        # SQLite needs check_same_thread=False for multi thread dev use
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        _engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True, connect_args=connect_args)
    return _engine

def init_db() -> None:
    engine = get_engine()
    metadata.create_all(engine)

if __name__ == "__main__":
    init_db()
    print("Tables created.")
