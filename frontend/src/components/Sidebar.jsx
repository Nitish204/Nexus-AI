import { useEffect, useRef, useState } from "react";
import { defaultProjectName } from "../utils/projectNaming";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("nexus_token");
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

// Groups projects into day-based buckets (Today / Yesterday / This
// Week / Older) instead of one long undifferentiated list — this is
// the "day to day history" grouping.
function groupByDay(projects) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const startOfWeek = new Date(startOfToday);
  startOfWeek.setDate(startOfWeek.getDate() - 7);

  const groups = { Today: [], Yesterday: [], "This Week": [], Older: [] };

  for (const p of projects) {
    const updated = new Date(p.updated_at || p.created_at);
    if (updated >= startOfToday) groups.Today.push(p);
    else if (updated >= startOfYesterday) groups.Yesterday.push(p);
    else if (updated >= startOfWeek) groups["This Week"].push(p);
    else groups.Older.push(p);
  }

  return Object.entries(groups).filter(([, items]) => items.length > 0);
}

function formatTime(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

const iconBtnStyle = {
  background: "none",
  border: "none",
  color: "#8fd9ec99",
  cursor: "pointer",
  fontSize: 12,
  padding: "2px 5px",
  borderRadius: 4,
};

export default function Sidebar({ user, currentProjectId, onSelectProject, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false); // mobile toggle
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  // Escape sets renamingId to null, which unmounts the input — but
  // removing a focused DOM node fires a native blur event just before
  // it disappears, and that blur handler calls commitRename() too.
  // Without this guard, cancelling via Escape would still silently
  // save the rename anyway. Set right before cancelling, checked and
  // cleared inside commitRename.
  const cancelingRenameRef = useRef(false);

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
      body: JSON.stringify({ name: defaultProjectName() }),
    });
    const data = await res.json();
    setProjects((prev) => [data, ...prev]);
    onSelectProject(data.id);
    setOpen(false);
  };

  const startRename = (p, e) => {
    e.stopPropagation();
    setRenamingId(p.id);
    setRenameValue(p.name || "");
  };

  const commitRename = async (id) => {
    if (cancelingRenameRef.current) {
      cancelingRenameRef.current = false;
      return;
    }
    const name = renameValue.trim();
    setRenamingId(null);
    if (!name) return;
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name } : p)));
    await fetch(`${API_BASE}/api/projects/${id}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify({ name }),
    }).catch(() => loadProjects());
  };

  const deleteProject = async (p, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${p.name || "this project"}"? This can't be undone.`)) return;
    setProjects((prev) => prev.filter((x) => x.id !== p.id));
    await fetch(`${API_BASE}/api/projects/${p.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).catch(() => loadProjects());
    if (p.id === currentProjectId) {
      const url = new URL(window.location.href);
      url.searchParams.delete("project");
      window.history.replaceState({}, "", url);
      window.location.reload();
    }
  };

  const grouped = groupByDay(
    [...projects].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
  );

  const content = (
    <div
      style={{
        width: 280,
        height: "100%",
        background: "#0a0d14",
        borderRight: "1px solid #ffffff14",
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        color: "#e6faff",
      }}
    >
      <div style={{ padding: "16px 16px 14px", borderBottom: "1px solid #ffffff14", display: "flex", alignItems: "center", gap: 10 }}>
        {user?.avatar_url ? (
          <img src={user.avatar_url} alt="" style={{ width: 34, height: 34, borderRadius: "50%", flexShrink: 0 }} />
        ) : (
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              background: "#00d9ff22",
              border: "1px solid #00d9ff44",
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
          <div style={{ fontSize: 11, color: "#8fd9ec80", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.email}
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Log out"
          style={{
            background: "none",
            border: "none",
            color: "#8fd9ec80",
            fontSize: 11,
            cursor: "pointer",
            padding: 4,
            flexShrink: 0,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#ff6b35")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#8fd9ec80")}
        >
          Logout
        </button>
      </div>

      <div style={{ padding: "14px 16px 10px" }}>
        <button
          onClick={createNewProject}
          style={{
            width: "100%",
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #00d9ff55",
            background: "#00d9ff14",
            color: "#00d9ff",
            fontWeight: 700,
            fontSize: 13,
            cursor: "pointer",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#00d9ff22")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#00d9ff14")}
        >
          + New Project
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "4px 10px 16px" }}>
        {loading && <div style={{ padding: "12px 6px", fontSize: 12, color: "#8fd9ec80" }}>Loading...</div>}
        {!loading && projects.length === 0 && (
          <div style={{ padding: "12px 6px", fontSize: 12, color: "#8fd9ec80" }}>No projects yet — create one above.</div>
        )}

        {grouped.map(([label, items]) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: "0.06em",
                fontWeight: 700,
                color: "#8fd9ec55",
                padding: "6px 6px 6px",
                textTransform: "uppercase",
              }}
            >
              {label}
            </div>
            {items.map((p) => {
              const isActive = p.id === currentProjectId;
              const isRenaming = renamingId === p.id;
              return (
                <div
                  key={p.id}
                  onClick={() => {
                    if (isRenaming) return;
                    onSelectProject(p.id);
                    setOpen(false);
                  }}
                  className="nexus-sidebar-item"
                  style={{
                    padding: "8px 8px",
                    borderRadius: 8,
                    marginBottom: 2,
                    cursor: isRenaming ? "default" : "pointer",
                    background: isActive ? "#00d9ff1a" : "transparent",
                    border: isActive ? "1px solid #00d9ff40" : "1px solid transparent",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    {isRenaming ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename(p.id);
                          if (e.key === "Escape") {
                            cancelingRenameRef.current = true;
                            setRenamingId(null);
                          }
                        }}
                        onBlur={() => commitRename(p.id)}
                        style={{
                          width: "100%",
                          background: "#05060a",
                          border: "1px solid #00d9ff66",
                          borderRadius: 4,
                          color: "#e6faff",
                          fontFamily: "monospace",
                          fontSize: 13,
                          padding: "2px 4px",
                        }}
                      />
                    ) : (
                      <>
                        <div
                          style={{
                            fontSize: 13,
                            color: isActive ? "#00d9ff" : "#e6faff",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {p.name || "Untitled Project"}
                        </div>
                        <div style={{ fontSize: 10, color: "#8fd9ec55" }}>
                          {formatTime(p.updated_at || p.created_at)}
                        </div>
                      </>
                    )}
                  </div>

                  {!isRenaming && (
                    <div style={{ display: "flex", gap: 2, opacity: 0, flexShrink: 0 }} className="nexus-sidebar-actions">
                      <button onClick={(e) => startRename(p, e)} title="Rename" style={iconBtnStyle}>
                        ✎
                      </button>
                      <button onClick={(e) => deleteProject(p, e)} title="Delete" style={{ ...iconBtnStyle, color: "#ff6b35" }}>
                        ✕
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <style>{`
        .nexus-sidebar-item:hover .nexus-sidebar-actions { opacity: 1 !important; }
      `}</style>
    </div>
  );

  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" ? window.innerWidth < 768 : false
  );

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <>
      {isMobile && !open && (
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
      )}

      {/* Renders exactly ONE live copy of `content` at a time — either
          the static desktop sidebar, or the mobile slide-over, never
          both mounted simultaneously (that duplication used to cause
          two copies of interactive elements like the rename input,
          both trying to autoFocus, existing in the DOM at once). */}
      {!isMobile && <div style={{ flexShrink: 0 }}>{content}</div>}

      {isMobile && open && (
        <div style={{ position: "fixed", inset: 0, zIndex: 40, display: "flex" }}>
          <div style={{ position: "relative", zIndex: 2 }}>{content}</div>
          <div style={{ flex: 1, background: "#00000088" }} onClick={() => setOpen(false)} />
        </div>
      )}
    </>
  );
}
