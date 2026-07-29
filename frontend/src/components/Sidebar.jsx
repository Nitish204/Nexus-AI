import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("nexus_token");
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export default function Sidebar({ user, currentProjectId, onSelectProject, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false); // mobile toggle

  const loadProjects = () => {
    setLoading(true);
    fetch(`${API_BASE}/api/projects`, { headers: authHeaders() })
      .then((res) => res.json())
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProjects();
  }, [currentProjectId]);

  const createNewProject = async () => {
    const res = await fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ name: "New Project" }),
    });
    const data = await res.json();
    onSelectProject(data.id);
    setOpen(false);
  };

  const content = (
    <div
      style={{
        width: 260,
        height: "100%",
        background: "#0a0d14f5",
        borderRight: "1px solid #00d9ff33",
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        color: "#e6faff",
      }}
    >
      {/* Account */}
      <div style={{ padding: 16, borderBottom: "1px solid #ffffff1a", display: "flex", alignItems: "center", gap: 10 }}>
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="" style={{ width: 36, height: 36, borderRadius: "50%" }} />
        ) : (
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "#00d9ff33",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              color: "#00d9ff",
            }}
          >
            {(user?.name || user?.email || "?")[0].toUpperCase()}
          </div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.name || "Account"}
          </div>
          <div style={{ fontSize: 11, color: "#8fd9ec99", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.email}
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Log out"
          style={{
            background: "none",
            border: "1px solid #ff6b3555",
            color: "#ff6b35",
            borderRadius: 6,
            padding: "4px 8px",
            fontSize: 11,
            cursor: "pointer",
          }}
        >
          Logout
        </button>
      </div>

      {/* New project */}
      <div style={{ padding: 12 }}>
        <button
          onClick={createNewProject}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #00d9ff66",
            background: "#00d9ff11",
            color: "#00d9ff",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          + New Project
        </button>
      </div>

      {/* Project list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 8px 12px" }}>
        <div style={{ fontSize: 11, color: "#8fd9ec66", padding: "8px 8px 4px" }}>RECENT PROJECTS</div>
        {loading && <div style={{ padding: 8, fontSize: 12, color: "#8fd9ec99" }}>Loading...</div>}
        {!loading && projects.length === 0 && (
          <div style={{ padding: 8, fontSize: 12, color: "#8fd9ec99" }}>No projects yet.</div>
        )}
        {projects
          .slice()
          .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
          .map((p) => (
            <div
              key={p.id}
              onClick={() => {
                onSelectProject(p.id);
                setOpen(false);
              }}
              style={{
                padding: "10px 10px",
                borderRadius: 8,
                marginBottom: 4,
                cursor: "pointer",
                background: p.id === currentProjectId ? "#00d9ff22" : "transparent",
                border: p.id === currentProjectId ? "1px solid #00d9ff55" : "1px solid transparent",
                fontSize: 13,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {p.name || "Untitled Project"}
            </div>
          ))}
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile toggle button */}
      <button
        onClick={() => setOpen(true)}
        style={{
          position: "fixed",
          top: 12,
          left: 12,
          zIndex: 30,
          display: window.innerWidth < 768 ? "flex" : "none",
          alignItems: "center",
          justifyContent: "center",
          width: 36,
          height: 36,
          borderRadius: 8,
          border: "1px solid #00d9ff66",
          background: "#0a0d14dd",
          color: "#00d9ff",
          fontSize: 18,
          cursor: "pointer",
        }}
      >
        ☰
      </button>

      {/* Desktop: static sidebar */}
      <div style={{ display: window.innerWidth < 768 ? "none" : "block", flexShrink: 0 }}>{content}</div>

      {/* Mobile: slide-over */}
      {open && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 40, display: window.innerWidth < 768 ? "flex" : "none" }}
        >
          <div style={{ position: "relative", zIndex: 2 }}>{content}</div>
          <div style={{ flex: 1 }} onClick={() => setOpen(false)} />
        </div>
      )}
    </>
  );
}
