from __future__ import annotations
from flask import Blueprint, jsonify, session
from datetime import timezone

from sqlalchemy import select, desc
from ..models import get_engine, plays, tracks, artists

bp = Blueprint("recent", __name__)

@bp.get("/api/recent")
def recent():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    eng = get_engine()
    with eng.begin() as conn:
        q = (
            select(
                plays.c.played_at,
                plays.c.elapsed_ms,
                plays.c.is_skip,
                tracks.c.title,
                tracks.c.album_name,
                artists.c.name.label("artist"),
            )
            .select_from(plays.join(tracks, plays.c.track_id == tracks.c.track_id).join(artists, tracks.c.artist_id == artists.c.artist_id))
            .where(plays.c.user_id == user_id)
            .order_by(desc(plays.c.played_at))
            .limit(20)
        )
        rows = conn.execute(q).mappings().all()

    data = [
        {
            "played_at": r["played_at"].isoformat(),
            "elapsed_ms": r["elapsed_ms"],
            "is_skip": r["is_skip"],
            "title": r["title"],
            "artist": r["artist"],
            "album": r["album_name"],
        }
        for r in rows
    ]
    return jsonify({"items": data})
