from __future__ import annotations
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, session
from sqlalchemy import select, func, and_, desc

from ..models import get_engine, plays, tracks, artists

bp = Blueprint("summary", __name__)

@bp.get("/api/summary/last30")
def summary_last30():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)

    eng = get_engine()
    with eng.begin() as conn:
        # totals
        s_ms = select(func.coalesce(func.sum(plays.c.elapsed_ms), 0)).where(
            and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now)
        )
        total_ms = conn.execute(s_ms).scalar_one()
        total_minutes = int(total_ms // 60000)

        s_plays = select(func.count()).where(
            and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now)
        )
        total_plays = conn.execute(s_plays).scalar_one()

        s_skips = select(func.count()).where(
            and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now, plays.c.is_skip.is_(True))
        )
        skips = conn.execute(s_skips).scalar_one()

        s_repeats = (
            select(func.count(), func.count(func.distinct(plays.c.track_id)))
            .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now))
        )
        tp, dt = conn.execute(s_repeats).fetchone()
        repeats = int(tp - dt)

        # top tracks by minutes
        s_top_tracks = (
            select(tracks.c.track_id, tracks.c.title, func.coalesce(func.sum(plays.c.elapsed_ms), 0).label("ms"))
            .select_from(plays.join(tracks, plays.c.track_id == tracks.c.track_id))
            .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now))
            .group_by(tracks.c.track_id, tracks.c.title)
            .order_by(desc("ms"))
            .limit(5)
        )
        top_tracks = [
            {"track_id": r.track_id, "title": r.title, "minutes": int(r.ms // 60000)}
            for r in conn.execute(s_top_tracks).fetchall()
        ]

        # top artists by minutes
        s_top_artists = (
            select(artists.c.artist_id, artists.c.name, func.coalesce(func.sum(plays.c.elapsed_ms), 0).label("ms"))
            .select_from(plays.join(tracks, plays.c.track_id == tracks.c.track_id).join(artists, tracks.c.artist_id == artists.c.artist_id))
            .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < now))
            .group_by(artists.c.artist_id, artists.c.name)
            .order_by(desc("ms"))
            .limit(5)
        )
        top_artists = [
            {"artist_id": r.artist_id, "name": r.name, "minutes": int(r.ms // 60000)}
            for r in conn.execute(s_top_artists).fetchall()
        ]

    return jsonify({
        "window": {"start": start.isoformat(), "end": now.isoformat()},
        "totals": {
            "minutes_listened": total_minutes,
            "plays": int(total_plays),
            "skips": int(skips),
            "repeats": repeats,
        },
        "top_tracks": top_tracks,
        "top_artists": top_artists,
    })
