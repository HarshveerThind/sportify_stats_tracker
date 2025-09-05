const BASE = "http://localhost:5000";

// Simple helper for GET and POST with credentials
export async function apiGet(path) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`GET ${path} ${res.status}`);
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  if (!res.ok) throw new Error(`POST ${path} ${res.status}`);
  return res.json();
}
