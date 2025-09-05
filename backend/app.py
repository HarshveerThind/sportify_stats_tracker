"""
Flask app:
- /login and /callback OAuth
- /refresh-token to rotate
- /sync-recent to run ingest then rollups
- registers API blueprints
"""

from __future__ import annotations
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from flask import Flask, jsonify, redirect, request, session
from flask_cors import CORS
from dotenv import load_dotenv

import requests
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import get_engine, user_info, now_utc
from .services.spotify import current_session_token, mint_access_token, sget
from .services.ingest import sync_recent_core
from .services.rollups import rollup_days

from .routes.recent import bp as recent_bp
from .routes.summary import bp as summary_bp
from .routes.heatmap import bp as heatmap_bp
from .routes.skipped import bp as skipped_bp
from .routes.export import bp as export_bp

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5000/callback")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

SCOPES = "user-read-private user-read-email user-read-recently-played user-top-read"

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY
    # cookies ok for http://localhost:5173 during dev
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=False)

    # CORS for Vite dev server
    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173"]}}, supports_credentials=True)
    CORS(app, resources={r"/login": {"origins": ["http://localhost:5173"]}}, supports_credentials=True)
    CORS(app, resources={r"/sync-recent": {"origins": ["http://localhost:5173"]}}, supports_credentials=True)

    # Blueprints
    app.register_blueprint(recent_bp)
    app.register_blueprint(summary_bp)
    app.register_blueprint(heatmap_bp)
    app.register_blueprint(skipped_bp)
    app.register_blueprint(export_bp)

    @app.get("/")
    def index():
        return jsonify({"ok": True, "message": "Backend up"})

    @app.get("/login")
    def login():
        state = secrets.token_urlsafe(16)
        session["oauth_state"] = state
        params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "show_dialog": "false",
        }
        url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return redirect(url)

    @app.get("/callback")
    def callback():
        code = request.args.get("code")
        state = request.args.get("state")
        if not code or not state or state != session.get("oauth_state"):
            return jsonify({"error": "invalid_state"}), 400

        # Exchange code for tokens
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        resp = requests.post(SPOTIFY_TOKEN_URL, data=data, timeout=10)
        if resp.status_code != 200:
            return jsonify({"error": "token_exchange_failed", "details": resp.text}), 400
        payload = resp.json()
        access_token = payload["access_token"]
        refresh_token = payload["refresh_token"]
        expires_in = int(payload.get("expires_in", 3600))

        # Get profile
        me = sget("me", access_token)
        uid = me["id"]
        display_name = me.get("display_name")
        email = me.get("email")
        country = me.get("country")
        profile_image = None
        images = me.get("images") or []
        if images:
            profile_image = images[0].get("url")

        # Upsert user with refresh token
        with get_engine().begin() as conn:
            stmt = sqlite_insert(user_info).values(
                user_id=uid,
                display_name=display_name,
                email=email,
                profile_image=profile_image,
                country=country,
                refresh_token=refresh_token,
            ).on_conflict_do_update(
                index_elements=[user_info.c.user_id],
                set_={
                    "display_name": display_name,
                    "email": email,
                    "profile_image": profile_image,
                    "country": country,
                    "refresh_token": refresh_token,  # rotate if new
                    "updated_at": now_utc(),
                }
            )
            conn.execute(stmt)

        # Store session token only in session
        session["user_id"] = uid
        session["access_token"] = access_token
        session["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        # redirect back to frontend
        return redirect("http://localhost:5173")

    @app.post("/refresh-token")
    def refresh_token_route():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401

        # Load current refresh_token
        with get_engine().begin() as conn:
            row = conn.execute(select(user_info.c.refresh_token).where(user_info.c.user_id == user_id)).fetchone()
            if not row:
                return jsonify({"error": "no_refresh_token"}), 400
            rt = row[0]

        minted = mint_access_token(rt)
        if not minted:
            return jsonify({"error": "refresh_failed"}), 400

        access_token = minted["access_token"]
        expires_in = minted["expires_in"]
        session["access_token"] = access_token
        session["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        # rotate refresh token if present
        new_rt = minted.get("refresh_token")
        if new_rt:
            with get_engine().begin() as conn:
                conn.execute(
                    user_info.update()
                    .where(user_info.c.user_id == user_id)
                    .values(refresh_token=new_rt, updated_at=datetime.now(timezone.utc))
                )

        return jsonify({"ok": True, "expires_in": expires_in})

    @app.post("/sync-recent")
    def sync_recent():
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401

        token = current_session_token()
        if not token:
            return jsonify({"error": "no_valid_token"}), 401

        counts, days = sync_recent_core(user_id, token)
        roll = rollup_days(user_id, days)

        return jsonify({"counts": counts, "rollups": roll, "touched_days": [d.isoformat() for d in days]})

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
