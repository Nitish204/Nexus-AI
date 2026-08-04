import { useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars, Sparkles } from "@react-three/drei";
import Editor from "@monaco-editor/react";
import AgentNode, { CoreNode, ConnectionBeam } from "./AgentNode";
import { useNexusProject } from "../hooks/useNexusProject";
import { useVoiceCommand } from "../hooks/useVoiceCommand";
import AnalyticsPanel from "../components/AnalyticsPanel";

// Agents arranged in a pentagon constellation around the shared core,
// rather than scattered ad hoc — the layout itself now communicates that
// every specialist reports to, and draws from, the same intelligence.
const CORE_POSITION = [0, 0.3, -2];
const ORBIT_RADIUS = 3.4;
const AGENT_ROLES = ["product_manager", "frontend_engineer", "devops_engineer", "qa_engineer", "backend_engineer"];

function buildLayout() {
  return AGENT_ROLES.map((role, i) => {
    const angle = (i / AGENT_ROLES.length) * Math.PI * 2 - Math.PI / 2;
    const x = CORE_POSITION[0] + Math.cos(angle) * ORBIT_RADIUS;
    const y = CORE_POSITION[1] + Math.sin(angle) * ORBIT_RADIUS * 0.62;
    const z = CORE_POSITION[2] - 0.4;
    return { role, position: [x, y, z] };
  });
}

const ROLE_COLOR = {
  product_manager: "#ffb454",
  backend_engineer: "#22d3ee",
  frontend_engineer: "#c084fc",
  qa_engineer: "#34d399",
  devops_engineer: "#fb7185",
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
        background: "linear-gradient(160deg, #0a0620 0%, #150a35 38%, #0d1442 70%, #06081f 100%)",
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
          0%, 100% { box-shadow: 0 0 24px #7c3aed33; }
          50% { box-shadow: 0 0 36px #38bdf844; }
        }
        .nexus-build-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 24px #38bdf866; }
        .nexus-build-btn:active { transform: translateY(0); }
        .nexus-mic-btn:hover { filter: brightness(1.15); }
        @media (prefers-reduced-motion: reduce) {
          * { animation: none !important; transition: none !important; }
        }
      `}</style>

      {/* 3D constellation + floating panels — fills all space above the command bar */}
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <Canvas camera={{ position: [0, 0.6, 9], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <pointLight position={[6, 6, 6]} intensity={1.4} color="#38bdf8" />
          <pointLight position={[-6, -4, 4]} intensity={1} color="#c084fc" />
          <pointLight position={[0, -5, -4]} intensity={0.6} color="#fb7185" />
          <Stars radius={70} depth={45} count={2200} factor={2.6} fade speed={0.4} />
          <Sparkles count={50} scale={12} size={2.4} speed={0.35} color="#a5b4fc" opacity={0.5} />

          <CoreNode busy={busy} />

          {AGENT_LAYOUT.map((a) => {
            const active = activeRoles.has(a.role);
            return (
              <group key={a.role}>
                <ConnectionBeam from={CORE_POSITION} to={a.position} color={ROLE_COLOR[a.role]} active={active} />
                <AgentNode role={a.role} position={a.position} active={active} />
              </group>
            );
          })}

          <OrbitControls enablePan={false} minDistance={5} maxDistance={16} autoRotate autoRotateSpeed={0.35} />
        </Canvas>

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
          <AnalyticsPanel projectId={projectId} deploymentStatus={deploymentStatus} />
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
            border: "1px solid #38bdf855",
            display: "flex",
            flexDirection: "column",
            background: "#0a0620",
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
                      color: isShown ? "#7dd3fc" : "#a5b4fc88",
                      background: isShown ? "#38bdf81f" : "transparent",
                      border: "none",
                      borderRadius: "8px 8px 0 0",
                      borderBottom: isShown ? "2px solid #38bdf8" : "2px solid transparent",
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
          background: "rgba(10, 8, 28, 0.85)",
          backdropFilter: "blur(14px)",
          WebkitBackdropFilter: "blur(14px)",
          borderTop: "1px solid #7c3aed44",
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
            border: "1px solid #7c3aed66",
            background: "#150a3599",
            color: "#e9e4ff",
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
              padding: "12px 14px",
              borderRadius: 10,
              border: `1px solid ${listening ? "#fb7185" : "#38bdf866"}`,
              background: listening ? "#fb718522" : "#150a3599",
              color: listening ? "#fb7185" : "#38bdf8",
              cursor: "pointer",
              fontWeight: 700,
              transition: "filter 0.2s ease",
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
            border: "none",
            background: "linear-gradient(135deg, #38bdf8, #c084fc)",
            color: "#0a0620",
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
