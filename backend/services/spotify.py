"""
Spotify helpers:
- session token access with auto-refresh
- minting access tokens from refresh tokens
- robust GET with retry on 401, 429, and 5xx
"""

from __future__ import annotations
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Iterator

import requests
from flask import session
from dotenv import load_dotenv

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models import get_engine, user_info

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

DEFAULT_TIMEOUT = 10  # seconds

def _session_expired() -> bool:
    exp = session.get("expires_at")
    if not exp:
        return True
    # buffer to avoid edge expiry
    return datetime.now(timezone.utc) >= (datetime.fromisoformat(exp) - timedelta(seconds=30))

def _update_session_token(access_token: str, expires_in: int) -> None:
    session["access_token"] = access_token
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    session["expires_at"] = expires_at.isoformat()

def current_session_token() -> Optional[str]:
    """
    Returns a valid access token from the session.
    If expired, tries to refresh using DB refresh_token for the session user.
    """
    token = session.get("access_token")
    if token and not _session_expired():
        return token

    user_id = session.get("user_id")
    if not user_id:
        return None

    # Pull stored refresh token
    eng = get_engine()
    with eng.begin() as conn:
        row = conn.execute(select(user_info.c.refresh_token).where(user_info.c.user_id == user_id)).fetchone()
        if not row or not row[0]:
            return None
        rt = row[0]

    minted = mint_access_token(rt)
    if not minted:
        return None

    new_at = minted["access_token"]
    _update_session_token(new_at, minted["expires_in"])

    # If Spotify rotates refresh token, persist it
    new_rt = minted.get("refresh_token")
    if new_rt:
        with get_engine().begin() as conn:
            conn.execute(
                update(user_info)
                .where(user_info.c.user_id == user_id)
                .values(refresh_token=new_rt)
            )
    return new_at

def mint_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """
    Exchange refresh_token for a new access token.
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    try:
        resp = requests.post(SPOTIFY_TOKEN_URL, data=data, timeout=DEFAULT_TIMEOUT)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        # Standardize keys we care about
        return {
            "access_token": payload.get("access_token"),
            "expires_in": int(payload.get("expires_in", 3600)),
            "refresh_token": payload.get("refresh_token"),  # may or may not be present
            "scope": payload.get("scope"),
            "token_type": payload.get("token_type"),
        }
    except requests.RequestException:
        return None

def _auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def sget(path: str, token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safe GET with retries:
    - 401: refresh and retry once if in route context
    - 429: wait Retry-After once
    - 5xx: retry once after short sleep
    """
    url = path if path.startswith("http") else f"{SPOTIFY_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    tried_refresh = False
    tried_5xx = False
    tried_429 = False

    while True:
        try:
            resp = requests.get(url, headers=_auth_header(token), params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException:
            if tried_5xx:
                raise
            tried_5xx = True
            time.sleep(1.0)
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 401 and not tried_refresh:
            # Attempt refresh via session if available
            tried_refresh = True
            new = current_session_token()
            if new:
                token = new
                continue
            # Not in session or could not refresh
            resp.raise_for_status()

        if resp.status_code == 429 and not tried_429:
            tried_429 = True
            retry_after = int(resp.headers.get("Retry-After", "1"))
            time.sleep(max(retry_after, 1))
            continue

        if 500 <= resp.status_code < 600 and not tried_5xx:
            tried_5xx = True
            time.sleep(1.0)
            continue

        # Raise for other cases with clear message
        try:
            msg = resp.json()
        except Exception:
            msg = resp.text
        raise RuntimeError(f"Spotify GET failed {resp.status_code}: {msg}")

def spaginate(url: str, token: str) -> Iterator[Dict[str, Any]]:
    """
    Generator over Spotify paging object with next URLs.
    """
    current_url = url
    while current_url:
        page = sget(current_url, token, params=None)
        yield page
        current_url = page.get("next")
