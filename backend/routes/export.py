from __future__ import annotations
from datetime import datetime, timedelta, timezone
from flask import Blueprint, Response, session
from sqlalchemy import select, and_
import csv
from io import StringIO

from ..models import get_engine, daily_totals, tracks, artists

bp = Blueprint("export", __name__)

@bp.get("/api/export/last30.csv")
def export_last30():
    user_id = session.get("user_id")
    if not user_id:
        return Response("unauthorized\n", status=401, mimetype="text/plain")

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    start_day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)

    eng = get_engine()
    with eng.begin() as conn:
        q = (
            select(
                daily_totals.c.day,
                daily_totals.c.minutes_listened,
                daily_totals.c.repeats,
                daily_totals.c.skips,
                tracks.c.title,
                artists.c.name,
            )
            .select_from(
                daily_totals
                .outerjoin(tracks, daily_totals.c.top_track_id == tracks.c.track_id)
                .outerjoin(artists, daily_totals.c.top_artist_id == artists.c.artist_id)
            )
            .where(and_(daily_totals.c.user_id == user_id, daily_totals.c.day >= start_day, daily_totals.c.day <= now))
            .order_by(daily_totals.c.day)
        )
        rows = conn.execute(q).mappings().all()

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["day", "minutes_listened", "repeats", "skips", "top_track_title", "top_artist_name"])
    for r in rows:
        writer.writerow([
            r["day"].date().isoformat(),
            r["minutes_listened"],
            r["repeats"],
            r["skips"],
            r.get("title") or "",
            r.get("name") or "",
        ])

    csv_data = buf.getvalue()
    buf.close()
    return Response(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=last30.csv"})
