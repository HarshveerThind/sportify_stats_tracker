# app.py
# Flask app that handles Spotify OAuth, fetches Recently Played, and exposes a simple debug API.

from flask import Flask, redirect, request, jsonify, session
import requests
from dotenv import load_dotenv
import os
import urllib.parse
from datetime import datetime, timezone
from models import db, user_info, artists, tracks, plays
from sqlalchemy import insert, update, select, text
from sqlalchemy.exc import IntegrityError
import time

load_dotenv()

app = Flask(__name__)
# Use a real secret key in production. This is fine for local dev.
app.secret_key = "94ac6d79efad4980616c2f988b4f720a5c936dc874d6a0868499f45e7a7a9c84"

# OAuth and API constants from your .env
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE_URL = "https://api.spotify.com/v1/"

@app.route("/")
def index():
    # Simple entry to start OAuth
    return "welcome to my spotify app <a href='/login'>Log in with spotify</a>"

@app.route("/login")
def login():
    # Scopes give you access to user profile, email, top items, and recently played.
    scope = "user-read-private user-read-email user-top-read user-read-recently-played"
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": REDIRECT_URI,
        "show_dialog": True,  # force account chooser in dev
    }
    # Redirect the user to Spotify's authorization page.
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route("/callback")
def callback():
    # Spotify redirects here with either code or error.
    if "error" in request.args:
        return jsonify({"error": request.args["error"]})

    if "code" in request.args:
        # Exchange the authorization code for access and refresh tokens.
        req_body = {
            "code": request.args["code"],
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(TOKEN_URL, data=req_body, headers=headers)

        if response.status_code != 200:
            # If Spotify returns an error, show it to help debugging.
            return jsonify(response.json()), 400

        token_info = response.json()
        # Store short lived access token and long lived refresh token in the session.
        session["access_token"] = token_info["access_token"]
        session["refresh_token"] = token_info.get("refresh_token")
        # Use Spotify's expires_in instead of a hardcoded value.
        session["expires_at"] = datetime.now().timestamp() + token_info["expires_in"]

        # Fetch profile so we can identify the user and upsert user_info.
        me_response = requests.get(
            API_BASE_URL + "me",
            headers={"Authorization": f"Bearer {session['access_token']}"},
            timeout=15,
        )
        me = me_response.json()

        uid = me["id"]  # Spotify user id
        display_name = me.get("display_name")
        email = me.get("email")
        profile_image = (me.get("images") or [{}])[0].get("url")
        country = me.get("country")
        rt = session.get("refresh_token")

        # Upsert the user row. Store the refresh token on first login.
        # Only overwrite refresh_token if Spotify actually returned a new one.
        with db.begin() as conn:
            existing = conn.execute(
                select(user_info).where(user_info.c.user_id == uid)
            ).fetchone()

            vals = {
                "display_name": display_name,
                "email": email,
                "profile_image": profile_image,
                "country": country,
                "updated_at": datetime.now(timezone.utc),
            }
            if rt:
                vals["refresh_token"] = rt

            if existing:
                # Update the profile fields. Keep the original refresh token if Spotify did not send a new one.
                conn.execute(
                    update(user_info).where(user_info.c.user_id == uid).values(**vals)
                )
            else:
                # First time this user logs in. A refresh token must be present.
                if not rt:
                    return jsonify({"error": "No refresh token for new user"}), 400
                vals.update({"user_id": uid, "refresh_token": rt})
                conn.execute(insert(user_info).values(**vals))

        # Stash uid in session for later routes.
        session["user_id"] = uid
        # Kick off the first data sync.
        return redirect("/sync-recent")

@app.route("/refresh-token")
def refresh_token():
    # Refresh the short lived access token when expired.
    if "refresh_token" not in session:
        return redirect("/login")

    # Only refresh if expired to reduce calls.
    if time.time() >= session.get("expires_at", 0):
        req_body = {
            "grant_type": "refresh_token",
            "refresh_token": session["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.post(TOKEN_URL, data=req_body, headers=headers)
        response.raise_for_status()
        new_token_info = response.json()

        # Update tokens in session. Spotify may rotate the refresh token.
        session["access_token"] = new_token_info["access_token"]
        session["refresh_token"] = new_token_info.get("refresh_token", session["refresh_token"])
        session["expires_at"] = datetime.now().timestamp() + new_token_info["expires_in"]

    # After refresh, optionally redirect back to the route that asked for it.
    next_url = request.args.get("next")
    if next_url:
        return redirect(next_url)
    return "Token refreshed or still valid"

@app.route("/sync-recent")
def sync_recent():
    # Require a fresh access token before calling Spotify.
    if time.time() >= session.get("expires_at", 0):
        return redirect("/refresh-token?next=/sync-recent")
    if "access_token" not in session:
        return redirect("/login")

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "No user ID in session"}), 400

    try:
        # Read the cursor so we only fetch new plays after this time.
        with db.connect() as conn:
            user_row = conn.execute(
                select(user_info.c.last_recent_cursor).where(user_info.c.user_id == user_id)
            ).fetchone()
            last_cursor = user_row.last_recent_cursor if user_row else None

        # Build the API call. Use limit 50 which is the maximum per request.
        params = {"limit": 50}
        if last_cursor:
            # Spotify expects milliseconds since epoch, UTC.
            after_ms = int(last_cursor.replace(tzinfo=timezone.utc).timestamp() * 1000)
            params["after"] = after_ms

        headers = {"Authorization": f"Bearer {session['access_token']}"}
        response = requests.get(
            API_BASE_URL + "me/player/recently-played",
            headers=headers,
            params=params,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        items = data.get("items", [])
        if not items:
            # Nothing new since the last cursor.
            return jsonify({"message": "No new plays found", "count": 0})

        plays_inserted = 0
        newest_played_at = None

        # Write artists, tracks, and plays inside one transaction.
        with db.begin() as conn:
            for item in items:
                track_info = item["track"]
                track_id = track_info["id"]
                artist_info = track_info["artists"][0]     # primary artist only for v1
                artist_id = artist_info["id"]
                # Spotify gives ISO UTC. Make it a timezone aware datetime.
                played_at = datetime.fromisoformat(item["played_at"].replace("Z", "+00:00"))

                # Track the newest timestamp to advance the cursor later.
                if not newest_played_at or played_at > newest_played_at:
                    newest_played_at = played_at

                # Upsert artist. Genres are not present in Recently Played most of the time.
                exists_artist = conn.execute(
                    select(artists).where(artists.c.artist_id == artist_id)
                ).fetchone()
                if not exists_artist:
                    conn.execute(insert(artists).values({
                        "artist_id": artist_id,
                        "name": artist_info["name"],
                        "genres": None
                    }))

                # Upsert track with core fields.
                exists_track = conn.execute(
                    select(tracks).where(tracks.c.track_id == track_id)
                ).fetchone()
                if not exists_track:
                    conn.execute(insert(tracks).values({
                        "track_id": track_id,
                        "artist_id": artist_id,
                        "title": track_info["name"],
                        "album_name": track_info["album"]["name"],
                        "duration_ms": track_info["duration_ms"]
                    }))

                # Insert the play. Unique constraint prevents duplicates across runs.
                try:
                    conn.execute(insert(plays).values({
                        "user_id": user_id,
                        "track_id": track_id,
                        "played_at": played_at,
                        "elapsed_ms": None,  # will compute later
                        "is_skip": None      # will infer later
                    }))
                    plays_inserted += 1
                except IntegrityError:
                    # Duplicate user_id + played_at. Safe to ignore.
                    pass

            # Advance the cursor to the newest played_at we wrote.
            if newest_played_at:
                conn.execute(
                    update(user_info)
                    .where(user_info.c.user_id == user_id)
                    .values(last_recent_cursor=newest_played_at)
                )

        # Return small counts so you can confirm the run worked.
        return jsonify({
            "message": "Sync completed successfully",
            "plays_inserted": plays_inserted,
            "total_items_processed": len(items),
            "last_cursor_updated": newest_played_at.isoformat() if newest_played_at else None
        })

    except requests.RequestException as e:
        # Network or API error from Spotify.
        return jsonify({"error": f"Spotify API error: {str(e)}"}), 500
    except Exception as e:
        # Database or logic error.
        return jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route("/api/recent")
def api_recent():
    """Simple debug endpoint to view recent plays joined with track and artist."""
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]

    # Use a read connection for selects.
    with db.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT p.played_at, t.title, a.name AS artist_name, p.elapsed_ms, p.is_skip
                FROM plays p
                JOIN tracks t ON p.track_id = t.track_id
                JOIN artists a ON t.artist_id = a.artist_id
                WHERE p.user_id = :uid
                ORDER BY p.played_at DESC
                LIMIT 20
            """),
            {"uid": user_id},
        ).fetchall()

    # Serialize rows to JSON friendly dicts.
    plays_data = [
        {
            "played_at": r.played_at.isoformat(),
            "title": r.title,
            "artist": r.artist_name,
            "elapsed_ms": r.elapsed_ms,
            "is_skip": r.is_skip,
        }
        for r in rows
    ]
    return jsonify({"plays": plays_data})

if __name__ == "__main__":
    # Start the dev server.
    app.run(host="0.0.0.0", debug=True)
