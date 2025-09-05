import React from "react";

export default function Login() {
  const login = () => {
    // direct browser navigation so cookies flow through callback
    window.location.href = "http://localhost:5000/login";
  };
  return (
    <div className="card space-y-4">
      <h2 className="text-xl font-semibold">Connect your Spotify</h2>
      <p>Click the button to authorize.</p>
      <button onClick={login} className="btn">Authorize with Spotify</button>
    </div>
  );
}
