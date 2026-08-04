import { useEffect, useRef, useState, useMemo } from "react";
import { defaultProjectName } from "../utils/projectNaming";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("nexus_token");
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

// Groups projects into day-based buckets (Today / Yesterday / This
// Week / Older) — the "day to day history" grouping.
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

// Live "time ago" so the sidebar keeps advancing instead of freezing at
// whatever it showed when the list last loaded — this needs a ticking
// `now` value (passed in) rather than computing once and forgetting it.
function formatRelative(dateStr, now) {
  const d = new Date(dateStr);
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const ACCENT = "#38bdf8";
const ACCENT_2 = "#c084fc";

const iconBtnStyle = {
  background: "none",
  border: "none",
  color: "#a5b4fc99",
  cursor: "pointer",
  fontSize: 12,
  padding: "4px 6px",
  borderRadius: 6,
  transition: "color 0.15s ease, background 0.15s ease",
};

export default function Sidebar({ user, currentProjectId, onSelectProject, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false); // mobile toggle
  const [search, setSearch] = useState("");
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [now, setNow] = useState(() => new Date());
  // Escape sets renamingId to null, which unmounts the input — but
  // removing a focused DOM node fires a native blur event just before
  // it disappears, and that blur handler calls commitRename() too.
  // Without this guard, cancelling via Escape would still silently
  // save the rename anyway. Set right before cancelling, checked and
  // cleared inside commitRename.
  const cancelingRenameRef = useRef(false);

  const loadProjects = () => {
    fetch(`${API_BASE}/api/projects`, { headers: authHeaders() })
      .then((res) => res.json())
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  // Initial load + reload whenever the open project changes (e.g. a
  // rename or new command elsewhere may have touched updated_at).
  useEffect(() => {
    setLoading(true);
    loadProjects();
  }, [currentProjectId]);

  // Keep the list quietly fresh in the background — this is what makes
  // "time ago" and ordering actually reflect activity (like a command
  // running in the currently open project) instead of only updating
  // the moment you switch projects.
  useEffect(() => {
    const poll = setInterval(loadProjects, 15000);
    return () => clearInterval(poll);
  }, []);

  // Tick the clock every 30s so relative timestamps ("2m ago" → "3m
  // ago") visibly advance without needing a full data reload.
  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(tick);
  }, []);

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

  // Selecting a project only ever changes which id is "current" — the
  // actual per-project data (files, activity, tasks) is loaded fresh by
  // useNexusProject whenever that id changes, so project1 vs project2
  // never bleed into each other here.
  const selectProject = (id) => {
    if (id === currentProjectId) {
      setOpen(false);
      return;
    }
    onSelectProject(id);
    setOpen(false);
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return projects;
    return projects.filter((p) => (p.name || "untitled project").toLowerCase().includes(q));
  }, [projects, search]);

  const grouped = groupByDay([...filtered].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at)));

  const content = (
    <div
      style={{
        width: 292,
        height: "100%",
        background: "linear-gradient(180deg, rgba(13,9,38,0.97) 0%, rgba(9,6,26,0.97) 100%)",
        backdropFilter: "blur(18px)",
        WebkitBackdropFilter: "blur(18px)",
        borderRight: "1px solid rgba(124,58,237,0.22)",
        display: "flex",
        flexDirection: "column",
        fontFamily: "'Space Grotesk', 'Segoe UI', sans-serif",
        color: "#e9e4ff",
      }}
    >
      {/* Account header */}
      <div
        style={{
          padding: "18px 18px 16px",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          alignItems: "center",
          gap: 11,
        }}
      >
        {user?.avatar_url ? (
          <img
            src={user.avatar_url}
            alt=""
            style={{ width: 36, height: 36, borderRadius: "50%", flexShrink: 0, border: "1.5px solid rgba(56,189,248,0.5)" }}
          />
        ) : (
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: 14,
              color: "#0a0620",
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
          <div style={{ fontSize: 11, color: "#a5b4fc80", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.email}
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Log out"
          style={{
            background: "none",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#a5b4fc99",
            fontSize: 10.5,
            fontWeight: 600,
            cursor: "pointer",
            padding: "5px 9px",
            borderRadius: 7,
            flexShrink: 0,
            transition: "color 0.15s ease, border-color 0.15s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#fb7185";
            e.currentTarget.style.borderColor = "rgba(251,113,133,0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "#a5b4fc99";
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)";
          }}
        >
          Logout
        </button>
      </div>

      {/* New project + search */}
      <div style={{ padding: "14px 16px 10px", display: "flex", flexDirection: "column", gap: 8 }}>
        <button
          onClick={createNewProject}
          className="nexus-new-project-btn"
          style={{
            width: "100%",
            padding: "11px 14px",
            borderRadius: 11,
            border: "none",
            background: `linear-gradient(135deg, ${ACCENT}, ${ACCENT_2})`,
            color: "#0a0620",
            fontWeight: 800,
            fontSize: 13,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            transition: "transform 0.18s ease, box-shadow 0.18s ease",
          }}
        >
          <span style={{ fontSize: 15, lineHeight: 1 }}>+</span> New Project
        </button>

        {projects.length > 4 && (
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects..."
            style={{
              width: "100%",
              padding: "8px 12px",
              borderRadius: 9,
              border: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.04)",
              color: "#e9e4ff",
              fontFamily: "inherit",
              fontSize: 12.5,
              outline: "none",
            }}
          />
        )}
      </div>

      {/* Project list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "6px 10px 16px" }}>
        {loading && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#a5b4fc80", display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                border: "2px solid rgba(165,180,252,0.3)",
                borderTopColor: ACCENT,
                display: "inline-block",
                animation: "nexusSpin 0.7s linear infinite",
              }}
            />
            Loading projects...
          </div>
        )}
        {!loading && filtered.length === 0 && projects.length > 0 && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#a5b4fc80" }}>No projects match "{search}".</div>
        )}
        {!loading && projects.length === 0 && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#a5b4fc80" }}>No projects yet — create one above.</div>
        )}

        {grouped.map(([label, items]) => (
          <div key={label} style={{ marginBottom: 16 }}>
            <div
              style={{
                fontSize: 10,
                letterSpacing: "0.08em",
                fontWeight: 700,
                color: "#a5b4fc55",
                padding: "8px 8px 7px",
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
                    selectProject(p.id);
                  }}
                  className="nexus-sidebar-item"
                  style={{
                    position: "relative",
                    padding: "9px 10px 9px 14px",
                    borderRadius: 10,
                    marginBottom: 3,
                    cursor: isRenaming ? "default" : "pointer",
                    background: isActive
                      ? "linear-gradient(90deg, rgba(56,189,248,0.14), rgba(192,132,252,0.08))"
                      : "transparent",
                    border: isActive ? "1px solid rgba(56,189,248,0.3)" : "1px solid transparent",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    transition: "background 0.15s ease, border-color 0.15s ease",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.035)";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = "transparent";
                  }}
                >
                  {isActive && (
                    <span
                      style={{
                        position: "absolute",
                        left: 0,
                        top: "22%",
                        bottom: "22%",
                        width: 3,
                        borderRadius: 3,
                        background: `linear-gradient(180deg, ${ACCENT}, ${ACCENT_2})`,
                      }}
                    />
                  )}
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
                          background: "#0a0620",
                          border: `1px solid ${ACCENT}88`,
                          borderRadius: 6,
                          color: "#e9e4ff",
                          fontFamily: "inherit",
                          fontSize: 13,
                          padding: "3px 6px",
                        }}
                      />
                    ) : (
                      <>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: isActive ? 700 : 500,
                            color: isActive ? "#e0f2fe" : "#e9e4ffcc",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {p.name || "Untitled Project"}
                        </div>
                        <div style={{ fontSize: 10.5, color: "#a5b4fc70", marginTop: 1 }}>
                          {formatRelative(p.updated_at || p.created_at, now)}
                        </div>
                      </>
                    )}
                  </div>

                  {!isRenaming && (
                    <div style={{ display: "flex", gap: 1, opacity: 0, flexShrink: 0 }} className="nexus-sidebar-actions">
                      <button
                        onClick={(e) => startRename(p, e)}
                        title="Rename"
                        style={iconBtnStyle}
                        onMouseEnter={(e) => (e.currentTarget.style.color = ACCENT)}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "#a5b4fc99")}
                      >
                        ✎
                      </button>
                      <button
                        onClick={(e) => deleteProject(p, e)}
                        title="Delete"
                        style={iconBtnStyle}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "#fb7185")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "#a5b4fc99")}
                      >
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

      <div style={{ padding: "10px 18px", borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: 10, color: "#a5b4fc55", textAlign: "center" }}>
        NEXUS · Autonomous AI developer workspace
      </div>

      <style>{`
        .nexus-sidebar-item:hover .nexus-sidebar-actions { opacity: 1 !important; }
        .nexus-new-project-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 22px rgba(56,189,248,0.35); }
        .nexus-new-project-btn:active { transform: translateY(0); }
        @keyframes nexusSpin { to { transform: rotate(360deg); } }
        @keyframes nexusSidebarSlide { 0% { transform: translateX(-100%); } 100% { transform: translateX(0); } }
        @media (prefers-reduced-motion: reduce) {
          * { animation: none !important; transition: none !important; }
        }
      `}</style>
    </div>
  );

  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" ? window.innerWidth < 768 : false);

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
            width: 38,
            height: 38,
            borderRadius: 10,
            border: "1px solid rgba(56,189,248,0.4)",
            background: "rgba(13,9,38,0.9)",
            backdropFilter: "blur(10px)",
            color: ACCENT,
            fontSize: 18,
            cursor: "pointer",
            boxShadow: "0 4px 18px rgba(0,0,0,0.4)",
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
          <div style={{ position: "relative", zIndex: 2, animation: "nexusSidebarSlide 0.25s cubic-bezier(0.22,1,0.36,1)" }}>
            {content}
          </div>
          <div style={{ flex: 1, background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)" }} onClick={() => setOpen(false)} />
        </div>
      )}
    </>
  );
}
