from __future__ import annotations
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, session
from sqlalchemy import select, and_, asc

from ..models import get_engine, daily_totals, tracks, artists

bp = Blueprint("heatmap", __name__)

def _parse_day(s: str) -> datetime:
    # Parse YYYY-MM-DD as UTC midnight
    dt = datetime.strptime(s, "%Y-%m-%d")
    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)

@bp.get("/api/heatmap")
def heatmap():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    end_default = datetime.now(timezone.utc)
    start_default = end_default - timedelta(days=30)
    start_param = request.args.get("start")
    end_param = request.args.get("end")

    start = _parse_day(start_param) if start_param else datetime(start_default.year, start_default.month, start_default.day, tzinfo=timezone.utc)
    end_day = _parse_day(end_param) if end_param else datetime(end_default.year, end_default.month, end_default.day, tzinfo=timezone.utc)

    eng = get_engine()
    with eng.begin() as conn:
        q = (
            select(
                daily_totals.c.day,
                daily_totals.c.minutes_listened,
                daily_totals.c.repeats,
                daily_totals.c.skips,
                daily_totals.c.top_track_id,
                daily_totals.c.top_artist_id,
                tracks.c.title,
                artists.c.name,
            )
            .select_from(
                daily_totals
                .outerjoin(tracks, daily_totals.c.top_track_id == tracks.c.track_id)
                .outerjoin(artists, daily_totals.c.top_artist_id == artists.c.artist_id)
            )
            .where(and_(daily_totals.c.user_id == user_id, daily_totals.c.day >= start, daily_totals.c.day <= end_day))
            .order_by(asc(daily_totals.c.day))
        )
        rows = conn.execute(q).mappings().all()

    data = []
    for r in rows:
        data.append({
            "day": r["day"].isoformat(),
            "minutes_listened": r["minutes_listened"],
            "repeats": r["repeats"],
            "skips": r["skips"],
            "top_track_id": r["top_track_id"],
            "top_artist_id": r["top_artist_id"],
            "top_track_title": r["title"],
            "top_artist_name": r["name"],
        })

    return jsonify({"items": data})
