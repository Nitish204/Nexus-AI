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
  product_manager: { color: "#ffb454", glow: "#ffb45488", label: "Product" },
  frontend_engineer: { color: "#ff8a65", glow: "#ff8a6588", label: "Frontend" },
  qa_engineer: { color: "#ffcc80", glow: "#ffcc8088", label: "QA" },
  backend_engineer: { color: "#4dd0e1", glow: "#4dd0e188", label: "Backend" },
  devops_engineer: { color: "#42a5f5", glow: "#42a5f588", label: "DevOps" },
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
        background: "radial-gradient(circle at 50% 40%, #111111 0%, #0a0a0a 55%, #050505 100%)",
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
          0%, 100% { box-shadow: 0 0 24px #ffffff11; }
          50% { box-shadow: 0 0 36px #4dd0e122; }
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
          0%, 100% { box-shadow: 0 0 0 0 #ffffff22, 0 0 18px 2px #ffffff1a; transform: translate(-50%, -50%) scale(1); }
          50% { box-shadow: 0 0 0 10px #ffffff00, 0 0 28px 6px #ffffff2a; transform: translate(-50%, -50%) scale(1.05); }
        }
        @keyframes nexusMicBreathe {
          0%, 100% { box-shadow: 0 0 0 0 #ffffff1a; }
          50% { box-shadow: 0 0 0 6px #ffffff00; }
        }
        .nexus-build-btn { background: #161616; border: 1px solid #2a2a2a; color: #d8d8d8; }
        .nexus-build-btn:hover {
          background: linear-gradient(135deg, #ffb454, #4dd0e1);
          color: #0a0a0a;
          border-color: transparent;
          transform: translateY(-1px);
          box-shadow: 0 6px 22px #00000055;
        }
        .nexus-build-btn:active { transform: translateY(0); }
        .nexus-mic-btn:hover { filter: brightness(1.2); }
        .nexus-agent-node { transition: filter 0.3s ease, transform 0.3s ease; }
        .nexus-agent-node.active { filter: brightness(1.4); transform: scale(1.12); }
        @media (prefers-reduced-motion: reduce) {
          * { animation: none !important; transition: none !important; }
        }
      `}</style>

      {/* Orbital core graph + floating panels — fills all space above the command bar */}
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "linear-gradient(#ffffff08 1px, transparent 1px), linear-gradient(90deg, #ffffff08 1px, transparent 1px)",
            backgroundSize: "34px 34px",
            maskImage: "radial-gradient(circle at 50% 55%, black 0%, transparent 72%)",
            WebkitMaskImage: "radial-gradient(circle at 50% 55%, black 0%, transparent 72%)",
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
                        width: 22,
                        height: 22,
                        borderRadius: "50%",
                        background: style.color,
                        boxShadow: active ? `0 0 22px 4px ${style.glow}` : `0 0 10px 1px ${style.glow}`,
                      }}
                    />
                    <span
                      style={{
                        fontSize: 10.5,
                        fontWeight: 600,
                        color: active ? style.color : "#8a8a8a",
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

          {/* Static connector lines from core to each orbit radius (visual field, not per-node tracking) */}
          <svg
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            viewBox="0 0 100 100"
          >
            <circle cx="50" cy="50" r="34" fill="none" stroke="#ffffff14" strokeWidth="0.4" />
          </svg>

          {/* Monochrome core, pulsing gently on its own — brighter while any agent is busy */}
          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: 46,
              height: 46,
              borderRadius: "50%",
              background: busy
                ? "radial-gradient(circle at 35% 30%, #ffffff, #cfcfcf 70%)"
                : "radial-gradient(circle at 35% 30%, #e8e8e8, #9a9a9a 70%)",
              animation: `nexusCorePulse ${busy ? 1.6 : 3.4}s ease-in-out infinite`,
            }}
          />
        </div>

        {/* Analytics panel — floats top-left over the canvas only */}
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 2,
            maxWidth: "calc(100vw - 24px)",
            opacity: mounted ? 1 : 0,
            animation: mounted ? "nexusPanelIn 0.55s cubic-bezier(0.22,1,0.36,1) 0.05s both" : "none",
          }}
        >
          <AnalyticsPanel projectId={projectId} deploymentStatus={deploymentStatus} files={fileList} />
        </div>

        {/* Code editor — floats top-right over the canvas only, shrinks on mobile */}
        <div
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
            border: "1px solid #ffffff22",
            display: "flex",
            flexDirection: "column",
            background: "#0a0a0a",
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
          background: "rgba(10, 10, 10, 0.85)",
          backdropFilter: "blur(14px)",
          WebkitBackdropFilter: "blur(14px)",
          borderTop: "1px solid #ffffff1a",
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
            padding: "12px 14px",
            borderRadius: 10,
            border: "1px solid #ffffff2a",
            background: "#141414",
            color: "#e8e8e8",
            fontFamily: "inherit",
            fontSize: 14,
            outline: "none",
          }}
        />
        {voiceSupported && (
          <button
            type="button"
            onClick={startListening}
            title="Voice command"
            className="nexus-mic-btn"
            style={{
              flexShrink: 0,
              width: 46,
              padding: 0,
              borderRadius: "50%",
              border: `1px solid ${listening ? "#ff8a65" : "#ffffff33"}`,
              background: listening ? "#ff8a65" : "#141414",
              color: listening ? "#0a0a0a" : "#c8c8c8",
              cursor: "pointer",
              fontWeight: 700,
              fontSize: 16,
              transition: "filter 0.2s ease, background 0.2s ease, border-color 0.2s ease",
              animation: listening ? "none" : "nexusMicBreathe 2.6s ease-in-out infinite",
            }}
          >
            {listening ? "●" : "🎙"}
          </button>
        )}
        <button
          type="submit"
          className="nexus-build-btn"
          style={{
            flexShrink: 0,
            padding: "12px 20px",
            borderRadius: 10,
            fontWeight: 800,
            cursor: "pointer",
            transition: "transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, color 0.2s ease",
          }}
        >
          Build →
        </button>
      </form>
    </div>
  );
}
