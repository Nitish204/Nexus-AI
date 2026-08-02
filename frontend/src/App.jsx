import Sidebar from "./components/Sidebar";
import { useEffect, useState } from "react";
import Workspace from "./scenes/Workspace";
import AuthPage from "./pages/AuthPage";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [user, setUser] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [projectId, setProjectId] = useState(
    new URLSearchParams(window.location.search).get("project") ?? ""
  );
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  // Validate any stored token on load
  useEffect(() => {
    const token = localStorage.getItem("nexus_token");
    if (!token) {
      setCheckingAuth(false);
      return;
    }
    fetch(`${API_BASE}/api/auth/me?token=${encodeURIComponent(token)}`)
      .then((res) => {
        if (!res.ok) throw new Error("expired");
        return res.json();
      })
      .then((data) => setUser(data))
      .catch(() => {
        localStorage.removeItem("nexus_token");
        localStorage.removeItem("nexus_user");
      })
      .finally(() => setCheckingAuth(false));
  }, []);

  // Auto-select the most recent project on login, or create one only if none exist
  useEffect(() => {
    if (!user || projectId || creating) return;
    setCreating(true);
    const token = localStorage.getItem("nexus_token");

    fetch(`${API_BASE}/api/projects`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => res.json())
      .then(async (existing) => {
        if (Array.isArray(existing) && existing.length > 0) {
          const mostRecent = existing
            .slice()
            .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))[0];
          const url = new URL(window.location.href);
          url.searchParams.set("project", mostRecent.id);
          window.history.replaceState({}, "", url);
          setProjectId(mostRecent.id);
          return;
        }
        // No projects exist yet for this user — create the first one
        const res = await fetch(`${API_BASE}/api/projects`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ name: "New Project" }),
        });
        const data = await res.json();
        const url = new URL(window.location.href);
        url.searchParams.set("project", data.id);
        window.history.replaceState({}, "", url);
        setProjectId(data.id);
      })
      .catch((err) => setError(err.message))
      .finally(() => setCreating(false));
  }, [user, projectId, creating]);

  const handleSelectProject = (id) => {
    const url = new URL(window.location.href);
    url.searchParams.set("project", id);
    window.history.replaceState({}, "", url);
    setProjectId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem("nexus_token");
    localStorage.removeItem("nexus_user");
    window.location.href = "/";
  };

  if (checkingAuth) {
    return (
      <div style={{ color: "#e6faff", fontFamily: "monospace", padding: 40, background: "#05060a", height: "100dvh" }}>
        Loading...
      </div>
    );
  }

  if (!user) {
    return <AuthPage onAuthenticated={(data) => setUser(data.user)} />;
  }

  if (error) {
    return (
      <div style={{ color: "#ff6b35", fontFamily: "monospace", padding: 40, background: "#05060a", height: "100dvh" }}>
        <h2>NEXUS — Couldn't start a project</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (!projectId) {
    return (
      <div style={{ display: "flex", height: "100dvh", background: "#05060a" }}>
        <Sidebar
          user={user}
          currentProjectId={null}
          onSelectProject={handleSelectProject}
          onLogout={handleLogout}
        />
        <div style={{ flex: 1, color: "#e6faff", fontFamily: "monospace", padding: 40 }}>
          <h2>NEXUS</h2>
          <p>Setting up your workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100dvh", background: "#05060a" }}>
      <Sidebar
        user={user}
        currentProjectId={projectId}
        onSelectProject={handleSelectProject}
        onLogout={handleLogout}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <Workspace projectId={projectId} />
      </div>
    </div>
  );
}
