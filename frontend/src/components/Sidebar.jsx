import { useEffect, useRef, useState, useMemo } from "react";
import { defaultProjectName } from "../utils/projectNaming";
import { apiFetch } from "../utils/api";

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

const ACCENT = "#7c3aed";
const ACCENT_2 = "#ff7a59";
const ACCENT_3 = "#4dd0c1";

const iconBtnStyle = {
  background: "none",
  border: "none",
  color: "#9a9aaa",
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
  const cancelingRenameRef = useRef(false);

  const loadProjects = () => {
    apiFetch(`/api/projects`)
      .then((res) => res.json())
      .then((data) => setProjects(Array.isArray(data) ? data : []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setLoading(true);
    loadProjects();
  }, [currentProjectId]);

  useEffect(() => {
    const poll = setInterval(loadProjects, 15000);
    return () => clearInterval(poll);
  }, []);

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(tick);
  }, []);

  const createNewProject = async () => {
    const res = await apiFetch(`/api/projects`, {
      method: "POST",
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
    await apiFetch(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }).catch(() => loadProjects());
  };

  const deleteProject = async (p, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${p.name || "this project"}"? This can't be undone.`)) return;
    const previous = projects;
    setProjects((prev) => prev.filter((x) => x.id !== p.id));
    try {
      const res = await apiFetch(`/api/projects/${p.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Delete failed (${res.status}).`);
      }
    } catch (err) {
      setProjects(previous);
      window.alert(`Couldn't delete "${p.name || "this project"}": ${err.message}`);
      return;
    }
    if (p.id === currentProjectId) {
      const url = new URL(window.location.href);
      url.searchParams.delete("project");
      window.history.replaceState({}, "", url);
      window.location.reload();
    }
  };

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
  const groupColors = [ACCENT, ACCENT_2, ACCENT_3];
  const todayCount = projects.filter((p) => new Date(p.updated_at || p.created_at) >= new Date(new Date().setHours(0, 0, 0, 0))).length;

  const content = (
    <div
      style={{
        width: 292,
        height: "100%",
        position: "relative",
        overflow: "hidden",
        background: "linear-gradient(180deg, #f3ecff 0%, #ffeee6 55%, #e6fbf6 100%)",
        borderRight: "1px solid #7c3aed14",
        display: "flex",
        flexDirection: "column",
        fontFamily: "'Space Grotesk', 'Segoe UI', sans-serif",
        color: "#2e2e3a",
      }}
    >
      <div style={{ position: "absolute", width: 220, height: 220, borderRadius: "50%", background: "radial-gradient(circle, #a78bfa66, transparent 70%)", top: -50, left: -40, animation: "nexusBlobFloat1 9s ease-in-out infinite", filter: "blur(6px)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", width: 190, height: 190, borderRadius: "50%", background: "radial-gradient(circle, #5eead455, transparent 70%)", bottom: 100, right: -40, animation: "nexusBlobFloat2 11s ease-in-out infinite", filter: "blur(6px)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", width: 150, height: 150, borderRadius: "50%", background: "radial-gradient(circle, #ffd66655, transparent 70%)", top: 280, left: -30, animation: "nexusBlobFloat2 13s ease-in-out infinite", filter: "blur(6px)", pointerEvents: "none" }} />

      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 8, padding: "16px 18px 4px" }}>
        <div style={{ position: "relative", width: 22, height: 22 }}>
          <div style={{ position: "absolute", inset: 0, border: "1.5px dashed #7c3aed55", borderRadius: "50%", animation: "nexusRingSpin 12s linear infinite" }} />
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "radial-gradient(circle at 32% 28%, #c4b5fd, #7c3aed 75%)",
              transform: "translate(-50%, -50%)",
              animation: "nexusLogoDotPulse 2.4s ease-in-out infinite",
            }}
          />
        </div>
        <span
          style={{
            fontSize: 13,
            fontWeight: 800,
            letterSpacing: "0.08em",
            background: "linear-gradient(120deg, #7c3aed, #ff7a59, #4dd0c1)",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          NEXUS
        </span>
      </div>

      <div
        style={{
          position: "relative",
          padding: "10px 18px 14px",
          borderBottom: "1px solid #7c3aed14",
          display: "flex",
          alignItems: "center",
          gap: 11,
        }}
      >
        {user?.avatar_url ? (
          <img
            src={user.avatar_url}
            alt=""
            style={{ width: 38, height: 38, borderRadius: "50%", flexShrink: 0, animation: "nexusAvatarGlow 2.6s ease-in-out infinite" }}
          />
        ) : (
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: "50%",
              background: "radial-gradient(circle at 32% 28%, #c4b5fd, #7c3aed 75%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: 14,
              color: "#ffffff",
              flexShrink: 0,
              animation: "nexusAvatarGlow 2.6s ease-in-out infinite",
            }}
          >
            {(user?.name || user?.email || "?")[0].toUpperCase()}
          </div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#2e2e3a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.name || "Account"}
          </div>
          <div style={{ fontSize: 11, color: "#8a8a9a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {user?.email}
          </div>
        </div>
        <button
          onClick={onLogout}
          title="Log out"
          className="nexus-glass"
          style={{
            border: "1px solid #ffffff",
            color: "#7c3aed",
            fontSize: 10.5,
            fontWeight: 700,
            cursor: "pointer",
            padding: "6px 11px",
            borderRadius: 8,
            flexShrink: 0,
            transition: "color 0.15s ease, border-color 0.15s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "#ff5c5c";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "#7c3aed";
          }}
        >
          Logout
        </button>
      </div>

      <div style={{ position: "relative", display: "flex", gap: 8, padding: "12px 18px 0" }}>
        <div className="nexus-glass" style={{ flex: 1, borderRadius: 10, padding: "8px 6px", textAlign: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: ACCENT }}>{projects.length}</div>
          <div style={{ fontSize: 9, color: "#9a9aaa", fontWeight: 600 }}>projects</div>
        </div>
        <div className="nexus-glass" style={{ flex: 1, borderRadius: 10, padding: "8px 6px", textAlign: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: ACCENT_2 }}>{todayCount}</div>
          <div style={{ fontSize: 9, color: "#9a9aaa", fontWeight: 600 }}>today</div>
        </div>
        <div className="nexus-glass" style={{ flex: 1, borderRadius: 10, padding: "8px 6px", textAlign: "center" }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: ACCENT_3 }}>{currentProjectId ? 1 : 0}</div>
          <div style={{ fontSize: 9, color: "#9a9aaa", fontWeight: 600 }}>open</div>
        </div>
      </div>

      <div style={{ position: "relative", padding: "14px 16px 10px", display: "flex", flexDirection: "column", gap: 8 }}>
        <button
          onClick={createNewProject}
          className="nexus-new-project-btn"
          style={{
            position: "relative",
            overflow: "hidden",
            width: "100%",
            padding: "12px 14px",
            borderRadius: 12,
            border: "none",
            background: "linear-gradient(120deg, #7c3aed, #ff7a59, #4dd0c1)",
            color: "#ffffff",
            fontWeight: 800,
            fontSize: 13,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            boxShadow: "0 10px 22px -8px #7c3aed55",
            transition: "transform 0.18s ease, box-shadow 0.18s ease",
          }}
        >
          <span style={{ fontSize: 15, lineHeight: 1 }}>✦</span> New Project
          <span className="nexus-btn-sheen" />
        </button>

        {projects.length > 4 && (
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects..."
            className="nexus-glass"
            style={{
              width: "100%",
              padding: "9px 12px",
              borderRadius: 10,
              border: "1px solid #ffffff",
              color: "#2e2e3a",
              fontFamily: "inherit",
              fontSize: 12.5,
              outline: "none",
            }}
          />
        )}
      </div>

      <div style={{ position: "relative", flex: 1, overflowY: "auto", padding: "6px 10px 16px" }}>
        {loading && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#8a8a9a", display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                border: "2px solid #7c3aed33",
                borderTopColor: ACCENT,
                display: "inline-block",
                animation: "nexusSpin 0.7s linear infinite",
              }}
            />
            Loading projects...
          </div>
        )}
        {!loading && filtered.length === 0 && projects.length > 0 && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#8a8a9a" }}>No projects match "{search}".</div>
        )}
        {!loading && projects.length === 0 && (
          <div style={{ padding: "14px 8px", fontSize: 12, color: "#8a8a9a" }}>No projects yet — create one above.</div>
        )}

        {grouped.map(([label, items], groupIdx) => (
          <div key={label} style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 8px 7px" }}>
              <div style={{ width: 5, height: 5, borderRadius: "50%", background: groupColors[groupIdx % groupColors.length] }} />
              <span
                style={{
                  fontSize: 10,
                  letterSpacing: "0.08em",
                  fontWeight: 700,
                  color: groupColors[groupIdx % groupColors.length],
                  textTransform: "uppercase",
                }}
              >
                {label}
              </span>
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
                  className={`nexus-sidebar-item${isActive ? " nexus-glass" : ""}`}
                  style={{
                    position: "relative",
                    padding: "10px 10px 10px 14px",
                    borderRadius: 12,
                    marginBottom: 5,
                    cursor: isRenaming ? "default" : "pointer",
                    border: isActive ? `1px solid ${ACCENT}33` : "1px solid transparent",
                    borderLeft: isActive ? `3px solid ${ACCENT}` : "3px solid transparent",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    transition: "background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.background = "#ffffff88";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.background = "transparent";
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
                          background: "#ffffff",
                          border: `1px solid ${ACCENT}88`,
                          borderRadius: 6,
                          color: "#2e2e3a",
                          fontFamily: "inherit",
                          fontSize: 13,
                          padding: "3px 6px",
                        }}
                      />
                    ) : (
                      <>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
                          <div
                            style={{
                              fontSize: 13,
                              fontWeight: isActive ? 700 : 500,
                              color: isActive ? "#2e2e3a" : "#3a3a4a",
                              whiteSpace: "nowrap",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                            }}
                          >
                            {p.name || "Untitled Project"}
                          </div>
                          {isActive && (
                            <span
                              style={{
                                fontSize: 9.5,
                                fontWeight: 700,
                                padding: "2px 7px",
                                borderRadius: 20,
                                background: `${ACCENT}1a`,
                                color: ACCENT,
                                flexShrink: 0,
                              }}
                            >
                              active
                            </span>
                          )}
                        </div>
                        {isActive && (
                          <div style={{ marginTop: 7, height: 4, borderRadius: 4, background: `${ACCENT}14`, overflow: "hidden" }}>
                            <div style={{ height: "100%", borderRadius: 4, background: `linear-gradient(90deg, ${ACCENT}, ${ACCENT_3})`, animation: "nexusBarGrow 1s ease-out both" }} />
                          </div>
                        )}
                        <div style={{ fontSize: 10.5, color: "#9a9aaa", marginTop: 4 }}>
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
                        onMouseLeave={(e) => (e.currentTarget.style.color = "#9a9aaa")}
                      >
                        ✎
                      </button>
                      <button
                        onClick={(e) => deleteProject(p, e)}
                        title="Delete"
                        style={iconBtnStyle}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "#ff5c5c")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "#9a9aaa")}
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

      <div style={{ position: "relative", padding: "10px 18px", borderTop: "1px solid #7c3aed14", fontSize: 10, color: "#9a9aaa", textAlign: "center" }}>
        NEXUS · Autonomous AI developer workspace
      </div>

      <style>{`
        .nexus-glass {
          background: #ffffffcc;
          backdrop-filter: blur(14px);
          -webkit-backdrop-filter: blur(14px);
          box-shadow: 0 14px 30px -12px #7c3aed22;
        }
        .nexus-sidebar-item:hover .nexus-sidebar-actions { opacity: 1 !important; }
        .nexus-new-project-btn:hover { transform: translateY(-1px); box-shadow: 0 14px 28px -6px #7c3aed77; }
        .nexus-new-project-btn:active { transform: translateY(0); }
        .nexus-btn-sheen {
          position: absolute; top: 0; left: 0; width: 40%; height: 100%;
          background: linear-gradient(120deg, transparent, #ffffff77, transparent);
          animation: nexusSheen 2.4s ease-in-out infinite;
        }
        @keyframes nexusSpin { to { transform: rotate(360deg); } }
        @keyframes nexusSidebarSlide { 0% { transform: translateX(-100%); } 100% { transform: translateX(0); } }
        @keyframes nexusBlobFloat1 { 0%, 100% { transform: translate(0,0) scale(1); } 50% { transform: translate(20px,-15px) scale(1.15); } }
        @keyframes nexusBlobFloat2 { 0%, 100% { transform: translate(0,0) scale(1); } 50% { transform: translate(-15px,20px) scale(1.1); } }
        @keyframes nexusRingSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes nexusLogoDotPulse { 0%, 100% { opacity: 0.5; transform: scale(1); } 50% { opacity: 1; transform: scale(1.3); } }
        @keyframes nexusAvatarGlow { 0%, 100% { box-shadow: 0 0 0 0 #7c3aed44; } 50% { box-shadow: 0 0 0 6px #7c3aed00; } }
        @keyframes nexusSheen { 0% { transform: translateX(-130%) skewX(-12deg); } 100% { transform: translateX(230%) skewX(-12deg); } }
        @keyframes nexusBarGrow { 0% { width: 0%; } 100% { width: 64%; } }
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
            border: "1px solid #ffffff",
            background: "#ffffffcc",
            backdropFilter: "blur(10px)",
            color: ACCENT,
            fontSize: 18,
            cursor: "pointer",
            boxShadow: "0 4px 18px -6px #7c3aed33",
          }}
        >
          ☰
        </button>
      )}

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
