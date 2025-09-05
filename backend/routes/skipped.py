from __future__ import annotations
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request, session
from sqlalchemy import select, func, and_, desc

from ..models import get_engine, plays, tracks, artists

bp = Blueprint("skipped", __name__)

def _parse_window(w: str) -> int:
    # supports "30d", "7d", "90d"
    try:
        days = int(w.strip().lower().replace("d", ""))
        return max(days, 1)
    except Exception:
        return 30

@bp.get("/api/most-skipped")
def most_skipped():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    w = request.args.get("window", "30d")
    days = _parse_window(w)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    eng = get_engine()
    with eng.begin() as conn:
        # per track counts and skip rate
        q = (
            select(
                tracks.c.track_id,
                tracks.c.title,
                artists.c.name.label("artist"),
                func.count().label("plays"),
                func.sum(func.case((plays.c.is_skip.is_(True), 1), else_=0)).label("skips"),
                func.coalesce(func.sum(plays.c.elapsed_ms), 0).label("ms"),
            )
            .select_from(plays.join(tracks, plays.c.track_id == tracks.c.track_id).join(artists, tracks.c.artist_id == artists.c.artist_id))
            .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now))
            .group_by(tracks.c.track_id, tracks.c.title, artists.c.name)
            .order_by(desc("skips"), desc("plays"))
            .limit(20)
        )
        rows = conn.execute(q).fetchall()

    items = []
    for r in rows:
        plays_count = int(r.plays or 0)
        skips = int(r.skips or 0)
        rate = float(skips / plays_count) if plays_count else 0.0
        items.append({
            "track_id": r.track_id,
            "title": r.title,
            "artist": r.artist,
            "plays": plays_count,
            "skips": skips,
            "skip_rate": round(rate, 3),
            "minutes": int((r.ms or 0) // 60000),
        })

    return jsonify({"window_days": days, "items": items})
