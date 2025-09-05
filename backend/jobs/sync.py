"""
Cron-friendly runner:
- loops users
- mints access token from stored refresh_token
- runs ingest and rollups
"""

from __future__ import annotations
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import select

from ..models import get_engine, user_info
from ..services.spotify import mint_access_token
from ..services.ingest import sync_recent_core
from ..services.rollups import rollup_days

load_dotenv()

def main():
    eng = get_engine()
    with eng.begin() as conn:
        users = conn.execute(select(user_info.c.user_id, user_info.c.refresh_token)).fetchall()

    for u in users:
        uid = u.user_id
        rt = u.refresh_token
        minted = mint_access_token(rt)
        if not minted:
            print(f"[{datetime.now(timezone.utc).isoformat()}] user={uid} refresh_failed")
            continue
        at = minted["access_token"]
        new_rt = minted.get("refresh_token")
        if new_rt:
            with eng.begin() as conn:
                conn.execute(user_info.update().where(user_info.c.user_id == uid).values(refresh_token=new_rt))

        counts, days = sync_recent_core(uid, at)
        roll = rollup_days(uid, days)
        print(f"[{datetime.now(timezone.utc).isoformat()}] user={uid} new={counts['new_plays']} updated_elapsed={counts['updated_elapsed']} rollup_rows={roll['rows_written']}")

if __name__ == "__main__":
    main()
