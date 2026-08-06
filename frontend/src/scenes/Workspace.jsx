import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { useNexusProject } from "../hooks/useNexusProject";
import { useVoiceCommand } from "../hooks/useVoiceCommand";
import AnalyticsPanel from "../components/AnalyticsPanel";

// "Orbital Core" theme — monochrome graphite stage, agents drift in a slow
// constant orbit around the shared core rather than sitting static. Warm
// (amber/coral) roles are the human-facing specialists; cool (teal/blue)
// roles are the systems specialists. The core itself stays monochrome so
// the two temperatures read as satellites orbiting a neutral intelligence.
const AGENT_ROLES = ["product_manager", "frontend_engineer", "devops_engineer", "qa_engineer", "backend_engineer"];
const ORBIT_PERIOD_S = 46; // one full slow revolution

function buildLayout() {
  return AGENT_ROLES.map((role, i) => ({
    role,
    angle: (i / AGENT_ROLES.length) * 360,
  }));
}

const ROLE_STYLE = {
  product_manager: { c1: "#ffcf9e", c2: "#ff9d5c", label: "Product" },
  frontend_engineer: { c1: "#ffb3a0", c2: "#ff6b5c", label: "Frontend" },
  qa_engineer: { c1: "#ffe89e", c2: "#ffcc5c", label: "QA" },
  backend_engineer: { c1: "#9ef2e0", c2: "#4dd0c1", label: "Backend" },
  devops_engineer: { c1: "#9ecfff", c2: "#3f9bff", label: "DevOps" },
};

// Infra artifacts (Dockerfile, compose, CI config) and test files are
// real outputs, but they aren't "the app" — a request like "build a
// to-do list in python" should land the editor on the to-do list code,
// not whatever DevOps or QA happened to finish last. These are only
// ever de-prioritized for the DEFAULT view; they're still selectable
// via the file tabs below.
function isSecondaryFile(path) {
  const p = path.toLowerCase();
  return (
    p.startsWith("tests/") ||
    p.includes("/tests/") ||
    p.startsWith("test_") ||
    p.endsWith(".dockerfile") ||
    p === "dockerfile" ||
    p.includes("docker-compose") ||
    p.includes(".github/workflows") ||
    p.endsWith(".yml") ||
    p.endsWith(".yaml")
  );
}

// Only the roles that write the actual requested product code — DevOps
// and QA output is real but shouldn't silently take over the main
// editor while a build is in progress.
const PRIMARY_CODE_ROLES = new Set(["backend_engineer", "frontend_engineer"]);

export default function Workspace({ projectId }) {
  const { agentActivity, taskStatuses, deploymentStatus, files, sendCommand } = useNexusProject(projectId);
  const [command, setCommand] = useState("");
  const [activeCode, setActiveCode] = useState("# Generated code will stream in here...");
  const [mounted, setMounted] = useState(false);
  const [selectedPath, setSelectedPath] = useState(null); // manual file tab override

  const AGENT_LAYOUT = useMemo(buildLayout, []);

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Forget the manually-picked file tab when switching projects — it
  // belonged to the previous project's file list, not this one's.
  useEffect(() => {
    setSelectedPath(null);
  }, [projectId]);

  // Voice greeting on load
  useEffect(() => {
    const lines = [
      "Welcome back.",
      "Nexus is online.",
      "Your intelligent engineering workspace has been fully initialized.",
      "Project management, architecture, frontend, backend, quality assurance, and DevOps specialists are standing by.",
      "Share your vision.",
      "And let's build something extraordinary.",
    ];

    let index = 0;
    let cancelled = false;

    const pickDeepMaleVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      if (!voices.length) return null;

      const preferredNames = [
        "Google UK English Male",
        "Microsoft David",
        "Microsoft Guy",
        "Daniel",
        "Fred",
        "Aaron",
        "Gordon",
        "Arthur",
      ];
      for (const name of preferredNames) {
        const match = voices.find((v) => v.name.includes(name));
        if (match) return match;
      }

      const genericMale = voices.find((v) => /male/i.test(v.name) && !/female/i.test(v.name));
      if (genericMale) return genericMale;

      return null;
    };

    const speakNext = () => {
      if (cancelled || index >= lines.length) return;
      const utterance = new SpeechSynthesisUtterance(lines[index]);
      const voice = pickDeepMaleVoice();
      if (voice) utterance.voice = voice;
      utterance.pitch = 0.65;
      utterance.rate = 0.92;
      utterance.onend = () => {
        if (cancelled) return;
        index++;
        setTimeout(speakNext, 500);
      };
      window.speechSynthesis.speak(utterance);
    };

    const startTimer = setTimeout(() => {
      if (cancelled) return;
      if (window.speechSynthesis.getVoices().length === 0) {
        window.speechSynthesis.onvoiceschanged = speakNext;
      } else {
        speakNext();
      }
    }, 0);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      window.speechSynthesis.onvoiceschanged = null;
      window.speechSynthesis.cancel();
    };
  }, []);

  const { start: startListening, listening, supported: voiceSupported } = useVoiceCommand((transcript) => {
    setCommand(transcript);
    sendCommand(transcript);
  });

  const activeRoles = new Set(
    Object.values(taskStatuses)
      .filter((t) => t.status === "in_progress")
      .map((t) => t.role)
  );
  const busy = activeRoles.size > 0;

  const fileList = Object.values(files);
  const sortedFiles = [...fileList].sort(
    (a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
  );

  // Default file: most recently updated PRODUCT file (skip Dockerfiles,
  // CI config, and tests) — falling back to any file at all only if
  // that's genuinely everything the project has.
  const primaryFile = sortedFiles.find((f) => !isSecondaryFile(f.path)) ?? sortedFiles[0] ?? null;
  const selectedFile = selectedPath ? files[selectedPath] : null;
  const mostRecentFile = selectedFile ?? primaryFile;

  // Only let a live-streaming "code" message pre-empt the saved file
  // view if it's from a product agent (Backend/Frontend) — a DevOps or
  // QA stream chunk finishing later should never hijack the editor away
  // from the code the person actually asked for.
  const latestCodeStream = selectedPath
    ? null
    : [...agentActivity].reverse().find((a) => a.message_type === "code" && PRIMARY_CODE_ROLES.has(a.role));

  const displayedCode = latestCodeStream?.content ?? mostRecentFile?.content ?? activeCode;
  const displayedLanguage = mostRecentFile?.language ?? "python";

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100dvh",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(160deg, #f3ecff 0%, #ffeee6 45%, #e6fbf6 100%)",
        fontFamily: "'Space Grotesk', 'Segoe UI', sans-serif",
      }}
    >
      <style>{`
        @keyframes nexusPanelIn {
          0% { opacity: 0; transform: translateY(-16px) scale(0.96); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes nexusBarIn {
          0% { opacity: 0; transform: translateY(16px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        @keyframes nexusGlowPulse {
          0%, 100% { box-shadow: 0 24px 60px -18px #7c3aed22, 0 0 0 1px #ffffff inset; }
          50% { box-shadow: 0 24px 60px -18px #7c3aed33, 0 0 24px -4px #4dd0c155, 0 0 0 1px #ffffff inset; }
        }
        @keyframes nexusOrbitSpin {
          0% { transform: translate(-50%, -50%) rotate(0deg); }
          100% { transform: translate(-50%, -50%) rotate(360deg); }
        }
        @keyframes nexusOrbitSpinReverse {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(-360deg); }
        }
        @keyframes nexusCorePulse {
          0%, 100% { box-shadow: 0 12px 30px -6px #7c3aed55, 0 0 0 0 #7c3aed22; transform: translate(-50%, -50%) scale(1); }
          50% { box-shadow: 0 16px 40px -6px #7c3aed77, 0 0 0 14px #7c3aed00; transform: translate(-50%, -50%) scale(1.06); }
        }
        @keyframes nexusSphereBob {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        @keyframes nexusActiveGlow {
          0%, 100% { box-shadow: 0 0 14px 4px currentColor, 0 8px 16px -4px #00000055; }
          50% { box-shadow: 0 0 28px 10px currentColor, 0 8px 16px -4px #00000055; }
        }
        @keyframes nexusBlob1 { 0%, 100% { transform: translate(0,0) scale(1); } 50% { transform: translate(30px,-20px) scale(1.15); } }
        @keyframes nexusBlob2 { 0%, 100% { transform: translate(0,0) scale(1); } 50% { transform: translate(-25px,25px) scale(1.1); } }
        @keyframes nexusBlob3 { 0%, 100% { transform: translate(0,0) scale(1); } 50% { transform: translate(20px,20px) scale(0.9); } }
        @keyframes nexusMicRing {
          0% { transform: scale(1); opacity: 0.5; }
          100% { transform: scale(2.1); opacity: 0; }
        }
        @keyframes nexusSheen {
          0% { transform: translateX(-120%) skewX(-12deg); }
          100% { transform: translateX(220%) skewX(-12deg); }
        }
        .nexus-glass {
          background: #ffffffcc;
          backdrop-filter: blur(18px);
          -webkit-backdrop-filter: blur(18px);
          border: 1px solid #ffffff;
          box-shadow: 0 20px 40px -14px #7c3aed22, 0 2px 0 #ffffff inset;
        }
        .nexus-build-btn {
          position: relative;
          overflow: hidden;
          background: linear-gradient(120deg, #7c3aed, #ff7a59, #4dd0c1);
          border: none;
          color: #ffffff;
          box-shadow: 0 10px 24px -6px #7c3aed55;
          letter-spacing: 0.02em;
        }
        .nexus-build-btn::after {
          content: "";
          position: absolute;
          top: 0; left: 0;
          width: 40%; height: 100%;
          background: linear-gradient(120deg, transparent, #ffffff77, transparent);
          animation: nexusSheen 2.4s ease-in-out infinite;
        }
        .nexus-build-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 14px 30px -6px #7c3aed77;
        }
        .nexus-build-btn:active { transform: translateY(0); }
        .nexus-mic-btn:hover { filter: brightness(1.08); }
        .nexus-agent-node { transition: filter 0.3s ease, transform 0.3s ease; }
        .nexus-agent-node.active { filter: brightness(1.15); transform: scale(1.18); }
        @media (prefers-reduced-motion: reduce) {
          * { animation: none !important; transition: none !important; }
        }
      `}</style>

      {/* Orbital core graph + floating panels — fills all space above the command bar */}
      <div style={{ flex: 1, position: "relative", minHeight: 0, overflow: "hidden" }}>
        {/* Drifting aurora color blobs for a bright, alive backdrop instead of flat white */}
        <div style={{ position: "absolute", width: 280, height: 280, borderRadius: "50%", background: "radial-gradient(circle, #a78bfa88, transparent 70%)", top: -60, left: -40, animation: "nexusBlob1 9s ease-in-out infinite", filter: "blur(6px)" }} />
        <div style={{ position: "absolute", width: 240, height: 240, borderRadius: "50%", background: "radial-gradient(circle, #ff9d7a77, transparent 70%)", bottom: -40, right: -30, animation: "nexusBlob2 11s ease-in-out infinite", filter: "blur(6px)" }} />
        <div style={{ position: "absolute", width: 220, height: 220, borderRadius: "50%", background: "radial-gradient(circle, #5eead477, transparent 70%)", bottom: 40, left: 20, animation: "nexusBlob3 8s ease-in-out infinite", filter: "blur(6px)" }} />
        <div style={{ position: "absolute", width: 180, height: 180, borderRadius: "50%", background: "radial-gradient(circle, #ffd66688, transparent 70%)", top: 100, right: 60, animation: "nexusBlob3 10s ease-in-out infinite", filter: "blur(6px)" }} />

        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "linear-gradient(#7c3aed0a 1px, transparent 1px), linear-gradient(90deg, #7c3aed0a 1px, transparent 1px)",
            backgroundSize: "38px 38px",
            maskImage: "radial-gradient(circle at 50% 55%, black 0%, transparent 68%)",
            WebkitMaskImage: "radial-gradient(circle at 50% 55%, black 0%, transparent 68%)",
          }}
        />

        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "56%",
            width: "min(78vw, 380px)",
            height: "min(78vw, 380px)",
            transform: "translate(-50%, -50%)",
          }}
        >
          {/* Slowly, continuously orbiting ring of agent nodes */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: "100%",
              height: "100%",
              animation: `nexusOrbitSpin ${ORBIT_PERIOD_S}s linear infinite`,
            }}
          >
            {AGENT_LAYOUT.map((a) => {
              const style = ROLE_STYLE[a.role];
              const active = activeRoles.has(a.role);
              return (
                <div
                  key={a.role}
                  style={{
                    position: "absolute",
                    left: "50%",
                    top: "50%",
                    width: 0,
                    height: 0,
                    transform: `rotate(${a.angle}deg) translateX(min(35vw, 170px))`,
                  }}
                >
                  {/* counter-rotate so the node + label stay upright as the ring spins */}
                  <div
                    style={{
                      animation: `nexusOrbitSpinReverse ${ORBIT_PERIOD_S}s linear infinite`,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <div
                      className={`nexus-agent-node${active ? " active" : ""}`}
                      style={{
                        width: active ? 30 : 24,
                        height: active ? 30 : 24,
                        borderRadius: "50%",
                        background: `radial-gradient(circle at 30% 30%, ${style.c1}, ${style.c2} 70%)`,
                        boxShadow: `0 8px 16px -4px ${style.c2}88, inset -3px -3px 6px #00000022`,
                        color: style.c2,
                        animation: active
                          ? "nexusSphereBob 3.4s ease-in-out infinite, nexusActiveGlow 1s ease-in-out infinite"
                          : "nexusSphereBob 3.4s ease-in-out infinite",
                      }}
                    />
                    <span
                      style={{
                        fontSize: 10.5,
                        fontWeight: 700,
                        color: active ? style.c2 : "#8a8a9a",
                        letterSpacing: "0.03em",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {style.label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Static connector ring around the orbit radius */}
          <svg
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            viewBox="0 0 100 100"
          >
            <circle cx="50" cy="50" r="34" fill="none" stroke="#7c3aed22" strokeWidth="0.4" />
          </svg>

          {/* Soft ambient bloom behind the core for depth, then the glowing 3D core itself */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: 140,
              height: 140,
              transform: "translate(-50%, -50%)",
              borderRadius: "50%",
              background: "radial-gradient(circle, #7c3aed1a 0%, transparent 70%)",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: 48,
              height: 48,
              borderRadius: "50%",
              background: busy
                ? "radial-gradient(circle at 32% 28%, #ede9fe, #7c3aed 75%)"
                : "radial-gradient(circle at 32% 28%, #c4b5fd, #7c3aed 75%)",
              animation: `nexusCorePulse ${busy ? 1.6 : 3}s ease-in-out infinite`,
            }}
          />
        </div>

        {/* Analytics panel — floats top-left over the canvas only */}
        <div
          className="nexus-glass"
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 2,
            maxWidth: "calc(100vw - 24px)",
            borderRadius: 14,
            padding: 2,
            opacity: mounted ? 1 : 0,
            animation: mounted ? "nexusPanelIn 0.55s cubic-bezier(0.22,1,0.36,1) 0.05s both" : "none",
          }}
        >
          <AnalyticsPanel projectId={projectId} deploymentStatus={deploymentStatus} files={fileList} />
        </div>

        {/* Code editor — floats top-right over the canvas only, shrinks on mobile */}
        <div
          className="nexus-glass"
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            zIndex: 2,
            width: "min(420px, 46vw)",
            height: "min(300px, 36vh)",
            minWidth: 180,
            borderRadius: 14,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            opacity: mounted ? 1 : 0,
            animation: mounted
              ? "nexusPanelIn 0.55s cubic-bezier(0.22,1,0.36,1) 0.15s both, nexusGlowPulse 6s ease-in-out infinite"
              : "none",
          }}
        >
          {sortedFiles.length > 1 && (
            <div
              style={{
                display: "flex",
                gap: 2,
                padding: "6px 6px 0",
                overflowX: "auto",
                flexShrink: 0,
                borderBottom: "1px solid #ffffff12",
              }}
            >
              {sortedFiles.map((f) => {
                const isShown = f.path === (mostRecentFile?.path ?? primaryFile?.path);
                return (
                  <button
                    key={f.path}
                    onClick={() => setSelectedPath(f.path)}
                    title={f.path}
                    style={{
                      flexShrink: 0,
                      padding: "5px 10px",
                      fontSize: 10.5,
                      fontFamily: "'Space Grotesk', monospace",
                      fontWeight: isShown ? 700 : 500,
                      color: isShown ? "#4dd0e1" : "#8a8a8a",
                      background: isShown ? "#4dd0e11f" : "transparent",
                      border: "none",
                      borderRadius: "8px 8px 0 0",
                      borderBottom: isShown ? "2px solid #4dd0e1" : "2px solid transparent",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                      opacity: isSecondaryFile(f.path) ? 0.65 : 1,
                    }}
                  >
                    {f.path.split("/").pop()}
                  </button>
                );
              })}
            </div>
          )}
          <div style={{ flex: 1, minHeight: 0 }}>
            <Editor
              height="100%"
              theme="vs-dark"
              language={displayedLanguage}
              value={displayedCode}
              options={{ readOnly: true, fontSize: 11, minimap: { enabled: false } }}
            />
          </div>
        </div>
      </div>

      {/* Command bar — its own fixed row below the canvas, never overlaps, always visible */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!command.trim()) return;
          sendCommand(command);
          setCommand("");
        }}
        style={{
          flexShrink: 0,
          display: "flex",
          gap: 8,
          padding: "10px 12px",
          paddingBottom: "max(10px, env(safe-area-inset-bottom))",
          background: "linear-gradient(180deg, #ffffffee, #ffffff)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          borderTop: "1px solid #eee2ff",
          boxShadow: "0 -10px 30px -14px #7c3aed22",
          opacity: mounted ? 1 : 0,
          animation: mounted ? "nexusBarIn 0.55s cubic-bezier(0.22,1,0.36,1) 0.2s both" : "none",
        }}
      >
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder='e.g. "Build a Django auth system"'
          style={{
            flex: 1,
            minWidth: 0,
            padding: "13px 16px",
            borderRadius: 14,
            border: "1px solid #ece6ff",
            background: "#faf9ff",
            boxShadow: "0 2px 6px #7c3aed11 inset",
            color: "#3a3a4a",
            fontFamily: "inherit",
            fontSize: 14,
            outline: "none",
          }}
        />
        {voiceSupported && (
          <div style={{ position: "relative", width: 50, height: 50, flexShrink: 0 }}>
            {listening && (
              <>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: "50%",
                    border: "2px solid #ff7a59",
                    animation: "nexusMicRing 1.8s ease-out infinite",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: "50%",
                    border: "2px solid #ff7a59",
                    animation: "nexusMicRing 1.8s ease-out infinite 0.6s",
                  }}
                />
              </>
            )}
            <button
              type="button"
              onClick={startListening}
              title="Voice command"
              className="nexus-mic-btn"
              style={{
                position: "relative",
                width: 44,
                height: 44,
                margin: 3,
                padding: 0,
                borderRadius: "50%",
                border: "none",
                background: "radial-gradient(circle at 32% 28%, #ffcaa8, #ff7a59 75%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: "0 8px 18px -4px #ff7a5977",
                transition: "transform 0.15s ease",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <rect x="9" y="2" width="6" height="12" rx="3" fill="white" />
                <path d="M5 11a7 7 0 0 0 14 0" stroke="white" strokeWidth="2" strokeLinecap="round" fill="none" />
                <line x1="12" y1="18" x2="12" y2="22" stroke="white" strokeWidth="2" strokeLinecap="round" />
                <line x1="8" y1="22" x2="16" y2="22" stroke="white" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        )}
        <button
          type="submit"
          className="nexus-build-btn"
          style={{
            flexShrink: 0,
            padding: "13px 22px",
            borderRadius: 14,
            fontWeight: 800,
            cursor: "pointer",
            transition: "transform 0.2s ease, box-shadow 0.2s ease",
          }}
        >
          Build →
        </button>
      </form>
    </div>
  );
}
