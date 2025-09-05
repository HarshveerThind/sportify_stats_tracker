import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import "./index.css";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Recent from "./pages/Recent.jsx";
import Summary from "./pages/Summary.jsx";
import Heatmap from "./pages/Heatmap.jsx";

function Layout({ children }) {
  return (
    <div className="max-w-3xl mx-auto p-4 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Spotify Stats</h1>
        <nav className="flex gap-3">
          <Link className="btn" to="/">Home</Link>
          <Link className="btn" to="/recent">Recent</Link>
          <Link className="btn" to="/summary">Summary</Link>
          <Link className="btn" to="/heatmap">Heat map</Link>
        </nav>
      </header>
      <main>{children}</main>
      <footer className="text-sm text-slate-500">Local dev build</footer>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route index element={<Layout><Home /></Layout>} />
        <Route path="/login" element={<Layout><Login /></Layout>} />
        <Route path="/recent" element={<Layout><Recent /></Layout>} />
        <Route path="/summary" element={<Layout><Summary /></Layout>} />
        <Route path="/heatmap" element={<Layout><Heatmap /></Layout>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")).render(<App />);
