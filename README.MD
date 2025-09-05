# Spotify Stats Tracker

Small single-user Spotify stats tracker. Flask 3 backend with SQLAlchemy Core v2 and Requests. Vite + React + Tailwind frontend. Stores refresh_token only in DB, access tokens live in the session.

## Features

- Spotify OAuth login and profile upsert
- Recently played ingestion with pagination
- Per play elapsed time and skip inference
- Daily rollups for minutes, repeats, skips, top track, top artist
- 30 day summary and most skipped
- CSV export for last 30 days
- Optional cron job

## Tech

- Python 3.11
- Flask 3
- SQLAlchemy Core v2 on SQLite
- Requests
- Vite + React + Tailwind

## Env

Create `.env` from `.env.example`.

