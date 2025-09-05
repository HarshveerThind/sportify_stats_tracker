"""
Ingestion of Recently Played into tables:
- pulls pages since last cursor
- upserts artists and tracks
- inserts plays
- computes elapsed_ms and is_skip for all but newest
- fixes previous newest from last run using the first new play
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Set

from sqlalchemy import select, update, insert, and_, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .spotify import sget
from ..models import get_engine, user_info, artists, tracks, plays

RECENT_ENDPOINT = "me/player/recently-played"
MAX_LIMIT = 50

def _parse_dt(iso_str: str) -> datetime:
    # Spotify returns ISO with Z, python can parse with fromisoformat after replace
    # Example: 2024-01-02T03:04:05.678Z
    if iso_str.endswith("Z"):
        iso_str = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _to_millis(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def _skip_rule(elapsed_ms: int, duration_ms: int) -> bool:
    if elapsed_ms < 30_000:
        return True
    if elapsed_ms < 0.25 * duration_ms:
        return True
    return False

def sync_recent_core(user_id: str, access_token: str) -> Tuple[Dict[str, int], List[datetime]]:
    """
    Core ingestion used by routes and cron.
    Returns (counts, touched_days)
    """
    eng = get_engine()

    # Get cursor
    with eng.begin() as conn:
        row = conn.execute(
            select(user_info.c.last_recent_cursor).where(user_info.c.user_id == user_id)
        ).fetchone()
        cursor_dt = row[0] if row else None

    params = {"limit": MAX_LIMIT}
    if cursor_dt:
        params["after"] = _to_millis(cursor_dt)

    # Fetch first page
    data = sget(RECENT_ENDPOINT, access_token, params=params)
    items = data.get("items", [])

    # Follow 'next' while present and items are newer than cursor
    next_url = data.get("next")
    all_items = items[:]
    while next_url:
        page = sget(next_url, access_token, params=None)
        page_items = page.get("items", [])
        if not page_items:
            break
        # Items are in reverse chronological by Spotify. We still collect all.
        all_items.extend(page_items)
        next_url = page.get("next")

    if not all_items:
        return ({"new_plays": 0, "new_artists": 0, "new_tracks": 0, "updated_elapsed": 0}, [])

    # Normalize and filter to tracks only
    normalized = []
    for it in all_items:
        tr = it.get("track") or {}
        if tr.get("type") != "track":
            continue  # skip episodes
        played_at = _parse_dt(it["played_at"])
        normalized.append({
            "played_at": played_at,
            "track_id": tr["id"],
            "track_title": tr.get("name"),
            "album_name": (tr.get("album") or {}).get("name"),
            "duration_ms": int(tr.get("duration_ms") or 0),
            "artist_id": (tr.get("artists") or [{}])[0].get("id"),
            "artist_name": (tr.get("artists") or [{}])[0].get("name"),
        })

    if not normalized:
        return ({"new_plays": 0, "new_artists": 0, "new_tracks": 0, "updated_elapsed": 0}, [])

    # Sort ascending by played_at
    normalized.sort(key=lambda x: x["played_at"])

    # Upserts for artists and tracks
    new_artists = 0
    new_tracks = 0
    with eng.begin() as conn:
        # artists
        for a in { (n["artist_id"], n["artist_name"]) for n in normalized if n["artist_id"] }:
            stmt = sqlite_insert(artists).values(
                artist_id=a[0], name=a[1], genres=None
            ).on_conflict_do_nothing(index_elements=["artist_id"])
            res = conn.execute(stmt)
            new_artists += res.rowcount or 0

        # tracks
        for t in { (n["track_id"], n["artist_id"], n["track_title"], n["album_name"], n["duration_ms"]) for n in normalized }:
            stmt = sqlite_insert(tracks).values(
                track_id=t[0], artist_id=t[1], title=t[2], album_name=t[3], duration_ms=t[4]
            ).on_conflict_do_nothing(index_elements=["track_id"])
            res = conn.execute(stmt)
            new_tracks += res.rowcount or 0

    # Insert plays with unique guard
    new_plays = 0
    with eng.begin() as conn:
        for n in normalized:
            stmt = sqlite_insert(plays).values(
                user_id=user_id,
                track_id=n["track_id"],
                played_at=n["played_at"],
                elapsed_ms=None,  # compute below
                is_skip=None,
            ).on_conflict_do_nothing(
                index_elements=["user_id", "played_at"]
            )
            res = conn.execute(stmt)
            new_plays += res.rowcount or 0

    # Compute elapsed for pairs inside this batch regardless of duplicates
    # Update the earlier row's elapsed_ms and is_skip
    updated_elapsed = 0
    with eng.begin() as conn:
        for i in range(len(normalized) - 1):
            curr = normalized[i]
            nxt = normalized[i + 1]
            gap_ms = int((nxt["played_at"] - curr["played_at"]).total_seconds() * 1000)
            gap_ms = max(gap_ms, 0)
            elapsed_ms = min(gap_ms, curr["duration_ms"])
            is_skip = _skip_rule(elapsed_ms, curr["duration_ms"])
            upd = (
                update(plays)
                .where(
                    and_(
                        plays.c.user_id == user_id,
                        plays.c.played_at == curr["played_at"]
                    )
                )
                .values(elapsed_ms=elapsed_ms, is_skip=is_skip)
            )
            res = conn.execute(upd)
            updated_elapsed += res.rowcount or 0

    # Fix previous newest from earlier run if present
    touched_days: Set[datetime] = set()
    for n in normalized:
        day = datetime(n["played_at"].year, n["played_at"].month, n["played_at"].day, tzinfo=timezone.utc)
        touched_days.add(day)

    with eng.begin() as conn:
        first_new_time = normalized[0]["played_at"]
        prev_latest = conn.execute(
            select(plays.c.id, plays.c.played_at, plays.c.track_id)
            .where(
                and_(
                    plays.c.user_id == user_id,
                    plays.c.played_at < first_new_time
                )
            )
            .order_by(plays.c.played_at.desc())
            .limit(1)
        ).fetchone()

        if prev_latest:
            # Only update if elapsed_ms is null
            prev_row = conn.execute(
                select(plays.c.id, plays.c.elapsed_ms)
                .where(plays.c.id == prev_latest.id)
            ).fetchone()
            if prev_row and prev_row.elapsed_ms is None:
                tr = conn.execute(
                    select(tracks.c.duration_ms).where(tracks.c.track_id == prev_latest.track_id)
                ).fetchone()
                duration_ms = int(tr.duration_ms) if tr else 0
                gap_ms = int((first_new_time - prev_latest.played_at).total_seconds() * 1000)
                gap_ms = max(gap_ms, 0)
                elapsed_ms = min(gap_ms, duration_ms)
                is_skip = _skip_rule(elapsed_ms, duration_ms) if duration_ms else None
                res = conn.execute(
                    update(plays)
                    .where(plays.c.id == prev_latest.id)
                    .values(elapsed_ms=elapsed_ms, is_skip=is_skip)
                )
                updated_elapsed += res.rowcount or 0
                prev_day = datetime(prev_latest.played_at.year, prev_latest.played_at.month, prev_latest.played_at.day, tzinfo=timezone.utc)
                touched_days.add(prev_day)

    # Update cursor to newest played_at written
    newest = normalized[-1]["played_at"]
    with eng.begin() as conn:
        conn.execute(
            update(user_info)
            .where(user_info.c.user_id == user_id)
            .values(last_recent_cursor=newest)
        )

    counts = {
        "new_plays": new_plays,
        "new_artists": new_artists,
        "new_tracks": new_tracks,
        "updated_elapsed": updated_elapsed,
    }

    return counts, sorted(touched_days)
