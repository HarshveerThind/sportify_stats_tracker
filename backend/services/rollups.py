"""
Daily rollups for a set of days for a user.
"""

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable

from sqlalchemy import select, func, and_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models import get_engine, plays, tracks, daily_totals

def _day_bounds(day_dt: datetime) -> tuple[datetime, datetime]:
    # day_dt is expected at UTC midnight
    start = datetime(day_dt.year, day_dt.month, day_dt.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end

def rollup_days(user_id: str, days: Iterable[datetime]) -> Dict[str, int]:
    """
    Aggregate per UTC day and upsert into daily_totals.
    """
    eng = get_engine()
    wrote = 0
    for day in days:
        start, end = _day_bounds(day)
        with eng.begin() as conn:
            # total minutes
            s_total_ms = select(func.coalesce(func.sum(plays.c.elapsed_ms), 0)).where(
                and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < end)
            )
            total_ms = conn.execute(s_total_ms).scalar_one()
            minutes_listened = int(total_ms // 60000)

            # repeats = total plays minus distinct tracks
            s_total_plays = select(func.count()).where(
                and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < end)
            )
            s_distinct_tracks = select(func.count(func.distinct(plays.c.track_id))).where(
                and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < end)
            )
            total_plays = conn.execute(s_total_plays).scalar_one()
            distinct_tracks = conn.execute(s_distinct_tracks).scalar_one()
            repeats = int(total_plays - distinct_tracks)

            # skips
            s_skips = select(func.count()).where(
                and_(
                    plays.c.user_id == user_id,
                    plays.c.played_at >= start,
                    plays.c.played_at < end,
                    plays.c.is_skip.is_(True),
                )
            )
            skips = int(conn.execute(s_skips).scalar_one())

            # top track by summed elapsed
            s_top_track = (
                select(plays.c.track_id, func.coalesce(func.sum(plays.c.elapsed_ms), 0).label("ms"))
                .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < end))
                .group_by(plays.c.track_id)
                .order_by(func.sum(plays.c.elapsed_ms).desc())
                .limit(1)
            )
            top_track_row = conn.execute(s_top_track).fetchone()
            top_track_id = top_track_row.track_id if top_track_row else None

            # top artist via join on tracks
            s_top_artist = (
                select(tracks.c.artist_id, func.coalesce(func.sum(plays.c.elapsed_ms), 0).label("ms"))
                .select_from(plays.join(tracks, plays.c.track_id == tracks.c.track_id))
                .where(and_(plays.c.user_id == user_id, plays.c.played_at >= start, plays.c.played_at < end))
                .group_by(tracks.c.artist_id)
                .order_by(func.sum(plays.c.elapsed_ms).desc())
                .limit(1)
            )
            top_artist_row = conn.execute(s_top_artist).fetchone()
            top_artist_id = top_artist_row.artist_id if top_artist_row else None

            stmt = sqlite_insert(daily_totals).values(
                user_id=user_id,
                day=start,
                minutes_listened=minutes_listened,
                top_track_id=top_track_id,
                top_artist_id=top_artist_id,
                repeats=repeats,
                skips=skips,
            ).on_conflict_do_update(
                index_elements=[daily_totals.c.user_id, daily_totals.c.day],
                set_={
                    "minutes_listened": minutes_listened,
                    "top_track_id": top_track_id,
                    "top_artist_id": top_artist_id,
                    "repeats": repeats,
                    "skips": skips,
                },
            )
            conn.execute(stmt)
            wrote += 1

    return {"rows_written": wrote}
