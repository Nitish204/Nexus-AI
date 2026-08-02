import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("nexus_token");
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

function groupByDate(projects) {
  const groups = { Today: [], Yesterday: [], "This Week": [], Older: [] };
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  const startOfWeek = new Date(startOfToday.getTime() - 6 * 86400000);

  for (const p of projects) {
    const updated = new Date(p.updated_at || p.created_at);
    if (updated >= startOfToday) groups.Today.push(p);
    else if (updated >= startOfYesterday) groups.Yesterday.push(p);
    else if (updated >= startOfWeek) groups["This Week"].push(p);
    else groups.Older.push(p);
  }
  return groups;
}

export default function Sidebar({ user, currentProjectId, onSelectProject, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const isMobile = window.innerWidth < 768;

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
    const interval = setInterval(loadProjects, 15000);
    return () => clearInterval(interval);
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

  const sorted = projects.slice().sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
  const grouped = groupByDate(sorted);

  const content = (
    <div
      style={{
        width: 280,
        height: "100%",
        background: "linear-gradient(180deg, #0a0d14fa, #05060afa)",
        borderRight: "1px solid #00d9ff22",
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        color: "#e6faff",
      }}
    >
      {/* Account */}
      <div style={{ padding: "16px 14px", borderBottom: "1px solid #ffffff14", display: "flex", alignItems: "center", gap: 10 }}>
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="" style={{ width: 34, height: 34, borderRadius: "50%", flexShrink: 0 }} />
        ) : (
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              background: "linear-gradient(135deg, #00d9ff44, #39ffe022)",
              border: "1px solid #00d9ff55",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              color: "#00d9ff",
              flexShrink: 0,
            }}
          >
            {(user?.name || user?.email || "?")[0].toUpperCase()}
          </div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.name || "Account"}
          </div>
          <div style={{ fontSize: 10.5, color: "#8fd9ec99", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
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
            padding: "5px 9px",
            fontSize: 10.5,
            cursor: "pointer",
            flexShrink: 0,
          }}
        >
          Logout
        </button>
      </div>

      {/* New project */}
      <div style={{ padding: "12px 14px" }}>
        <button
          onClick={createNewProject}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 10,
            border: "1px solid #00d9ff55",
            background: "linear-gradient(135deg, #00d9ff18, #39ffe00c)",
            color: "#00d9ff",
            fontWeight: 700,
            fontSize: 13,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
          }}
        >
          <span style={{ fontSize: 16 }}>+</span> New Project
        </button>
      </div>

      {/* Grouped project list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 10px 16px" }}>
        {loading && <div style={{ padding: 10, fontSize: 12, color: "#8fd9ec99" }}>Loading...</div>}
        {!loading && sorted.length === 0 && (
          <div style={{ padding: 10, fontSize: 12, color: "#8fd9ec99" }}>No projects yet — start one above.</div>
        )}
        {!loading &&
          Object.entries(grouped).map(([label, items]) =>
            items.length === 0 ? null : (
              <div key={label} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 10.5, letterSpacing: 0.5, color: "#8fd9ec66", padding: "6px 8px 6px", fontWeight: 700 }}>
                  {label.toUpperCase()}
                </div>
                {items.map((p) => {
                  const active = p.id === currentProjectId;
                  return (
                    <div
                      key={p.id}
                      onClick={() => {
                        onSelectProject(p.id);
                        setOpen(false);
                      }}
                      style={{
                        padding: "10px 12px",
                        borderRadius: 10,
                        marginBottom: 4,
                        cursor: "pointer",
                        background: active ? "#00d9ff1f" : "transparent",
                        border: active ? "1px solid #00d9ff55" : "1px solid transparent",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={(e) => {
                        if (!active) e.currentTarget.style.background = "#ffffff0a";
                      }}
                      onMouseLeave={(e) => {
                        if (!active) e.currentTarget.style.background = "transparent";
                      }}
                    >
                      <div
                        style={{
                          fontSize: 12.5,
                          color: active ? "#00d9ff" : "#e6faff",
                          fontWeight: active ? 700 : 500,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {p.name && p.name !== "New Project" ? p.name : "Untitled Project"}
                      </div>
                      <div style={{ fontSize: 10, color: "#8fd9ec66", marginTop: 2 }}>
                        {new Date(p.updated_at || p.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          )}
      </div>
    </div>
  );

  if (isMobile) {
    return (
      <>
        <button
          onClick={() => setOpen(true)}
          style={{
            position: "fixed",
            top: 12,
            left: 12,
            zIndex: 30,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 38,
            height: 38,
            borderRadius: 10,
            border: "1px solid #00d9ff66",
            background: "#0a0d14dd",
            color: "#00d9ff",
            fontSize: 18,
            cursor: "pointer",
          }}
        >
          ☰
        </button>
        {open && (
          <div style={{ position: "fixed", inset: 0, zIndex: 40, display: "flex" }}>
            <div style={{ position: "relative", zIndex: 2, boxShadow: "10px 0 40px #000000aa" }}>{content}</div>
            <div style={{ flex: 1, background: "#00000066" }} onClick={() => setOpen(false)} />
          </div>
        )}
      </>
    );
  }

  return <div style={{ flexShrink: 0 }}>{content}</div>;
}
