import React, { useEffect, useState } from "react";
import { apiGet } from "../utils/api";

export default function Recent() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    apiGet("/api/recent")
      .then((d) => setItems(d.items))
      .catch(() => setErr("Failed to load. Try logging in then syncing."));
  }, []);

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-3">Recently played</h2>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <ul className="divide-y">
        {items.map((it, idx) => (
          <li key={idx} className="py-2">
            <div className="flex justify-between">
              <div>
                <div className="font-medium">{it.title}</div>
                <div className="text-sm text-slate-600">{it.artist}</div>
              </div>
              <div className="text-right text-sm">
                <div>{it.elapsed_ms !== null ? `${Math.round(it.elapsed_ms/1000)}s` : "..."}</div>
                <div className={it.is_skip ? "text-amber-700" : "text-slate-500"}>{it.is_skip ? "skip" : ""}</div>
              </div>
            </div>
            <div className="text-xs text-slate-500">{new Date(it.played_at).toLocaleString()}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
