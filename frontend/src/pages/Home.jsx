import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../utils/api";

export default function Home() {
  const [status, setStatus] = useState("");
  const [needsAuth, setNeedsAuth] = useState(false);

  useEffect(() => {
    // Probe auth. If 401, show connect card.
    apiGet("/api/recent")
      .then(() => setNeedsAuth(false))
      .catch(() => setNeedsAuth(true));
  }, []);

  const connect = () => {
    window.location.href = "http://localhost:5000/login";
  };

  const syncNow = async () => {
    setStatus("Syncing...");
    try {
      const res = await apiPost("/sync-recent");
      setStatus(`Synced. New plays ${res.counts.new_plays}, rollups ${res.rollups.rows_written}`);
    } catch {
      setStatus("Sync failed. Authorize first.");
    }
  };

  return (
    <div className="space-y-4">
      {needsAuth && (
        <div className="card space-y-3">
          <h2 className="text-xl font-semibold">Connect your Spotify</h2>
          <p className="text-sm text-slate-600">First time here. Click below to authorize.</p>
          <button className="btn" onClick={connect}>Authorize with Spotify</button>
        </div>
      )}

      <div className="card">
        <h2 className="text-xl font-semibold mb-2">Quick actions</h2>
        <div className="flex gap-3">
          <button className="btn" onClick={syncNow} disabled={needsAuth} aria-disabled={needsAuth}>
            Sync now
          </button>
          <a className="btn" href="http://localhost:5000/api/export/last30.csv" target="_blank" rel="noreferrer">
            Export last 30 days CSV
          </a>
        </div>
        {needsAuth && <p className="mt-3 text-sm text-amber-700">Authorize before syncing.</p>}
        {status && <p className="mt-3 text-sm text-slate-600">{status}</p>}
      </div>
    </div>
  );
}