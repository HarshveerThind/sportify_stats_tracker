import React, { useEffect, useState } from "react";
import { apiGet } from "../utils/api";

export default function Summary() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiGet("/api/summary/last30")
      .then(setData)
      .catch(() => setErr("Failed to load. Try syncing and reload."));
  }, []);

  if (err) return <div className="card">{err}</div>;
  if (!data) return <div className="card">Loading...</div>;

  const t = data.totals;

  return (
    <div className="space-y-4">
      <div className="card">
        <h2 className="text-xl font-semibold mb-2">Last 30 days</h2>
        <p>Minutes listened: <b>{t.minutes_listened}</b></p>
        <p>Plays: <b>{t.plays}</b> Skips: <b>{t.skips}</b> Repeats: <b>{t.repeats}</b></p>
      </div>
      <div className="card">
        <h3 className="font-semibold mb-2">Top tracks</h3>
        <ul className="list-disc pl-5">
          {data.top_tracks.map((x) => (
            <li key={x.track_id}>{x.title} — {x.minutes} min</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3 className="font-semibold mb-2">Top artists</h3>
        <ul className="list-disc pl-5">
          {data.top_artists.map((x) => (
            <li key={x.artist_id}>{x.name} — {x.minutes} min</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
