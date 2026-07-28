import { useEffect, useState } from "react";
import Workspace from "./scenes/Workspace";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [projectId, setProjectId] = useState(
    new URLSearchParams(window.location.search).get("project") ?? ""
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (projectId || creating) return;
    setCreating(true);
    fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New Project" }),
    })
      .then((res) => res.json())
      .then((data) => {
        const url = new URL(window.location.href);
        url.searchParams.set("project", data.id);
        window.history.replaceState({}, "", url);
        setProjectId(data.id);
      })
      .catch((err) => setError(err.message))
      .finally(() => setCreating(false));
  }, [projectId, creating]);

  if (error) {
    return (
      <div style={{ color: "#ff6b35", fontFamily: "monospace", padding: 40, background: "#05060a", height: "100vh" }}>
        <h2>NEXUS — Couldn't start a project</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div style={{ color: "#e6faff", fontFamily: "monospace", padding: 40, background: "#05060a", height: "100vh" }}>
        <h2>NEXUS</h2>
        <p>Setting up your workspace...</p>
      </div>
    );
  }

  return <Workspace projectId={projectId} />;
}
