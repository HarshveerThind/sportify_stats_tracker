import React, { useEffect, useState } from "react";
import { apiGet } from "../utils/api";

function formatDay(iso) {
  const d = new Date(iso);
  return d.toISOString().slice(0, 10);
}

export default function Heatmap() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiGet("/api/heatmap")
      .then((d) => setItems(d.items))
      .catch(() => setErr("Failed to load. Try syncing and reload."));
  }, []);

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-3">Daily heat map</h2>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <div className="grid grid-cols-1 gap-2">
        {items.map((d) => (
          <div key={d.day} className="flex items-center justify-between border rounded-lg p-2">
            <div className="text-sm">{formatDay(d.day)}</div>
            <div className="flex items-center gap-3">
              <div className="text-sm">min {d.minutes_listened}</div>
              <div className="text-sm">rep {d.repeats}</div>
              <div className="text-sm">skips {d.skips}</div>
              <div className="text-xs text-slate-600">{d.top_track_title ? `${d.top_track_title} • ${d.top_artist_name || ""}` : ""}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
