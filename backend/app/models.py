from sqlalchemy import String, Column, Table, create_engine, MetaData, ForeignKey, Boolean, Integer, Float, Date, DateTime, Text, func, UniqueConstraint
import os
from dotenv import load_dotenv

load_dotenv()

# Create the database engine
db = create_engine(os.getenv("DATABASE_URL", "sqlite:///stats.db"))
metadata = MetaData()

user_info = Table(
    "user_info",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("display_name", String),
    Column("email", String, nullable=True),
    Column("profile_image", String, nullable=True),
    Column("country", String, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now(), server_onupdate=func.now()),
    Column("refresh_token", String, nullable=False),
    Column("last_recent_cursor", DateTime, nullable=True)  # NEW: Track last sync point
)

artists = Table(
    "artists",
    metadata,
    Column("artist_id", String, primary_key=True),
    Column("name", String),
    Column("country", String, nullable=True),
    Column("genres", Text, nullable=True)
)

tracks = Table(
    "tracks",
    metadata,
    Column("track_id", String, primary_key=True),
    Column("artist_id", String, ForeignKey("artists.artist_id")),
    Column("title", String),
    Column("album_name", String),
    Column("duration_ms", Integer),
    Column("danceability", Float, nullable=True),
    Column("energy", Float, nullable=True),
    Column("tempo", Float, nullable=True),
    Column("valence", Float, nullable=True),
    Column("loudness", Float, nullable=True),
    Column("acousticness", Float, nullable=True)
)

plays = Table(
    "plays",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, ForeignKey("user_info.user_id"), nullable=False),
    Column("track_id", String, ForeignKey("tracks.track_id"), nullable=False),
    Column("played_at", DateTime, nullable=False),
    Column("elapsed_ms", Integer),
    Column("is_skip", Boolean),
    # NEW: Unique constraint to prevent duplicates
    UniqueConstraint('user_id', 'played_at', name='unique_user_play')
)

daily_totals = Table(
    "daily_totals",
    metadata,
    Column("user_id", String, ForeignKey("user_info.user_id"), primary_key=True),
    Column("day", Date, primary_key=True),
    Column("minutes_listened", Integer),
    Column("top_track_id", String, ForeignKey("tracks.track_id")),
    Column("top_artist_id", String, ForeignKey("artists.artist_id")),
    Column("repeats", Integer, nullable=True),
    Column("skips", Integer, nullable=True)
)

def init_db():
    """Create tables if they do not exist."""
    metadata.create_all(bind=db)

if __name__ == "__main__":
    init_db()
    print("DB initialized")