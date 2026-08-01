import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars, Html } from "@react-three/drei";
import Editor from "@monaco-editor/react";
import AgentNode from "./AgentNode";
import { useNexusProject } from "../hooks/useNexusProject";
import { useVoiceCommand } from "../hooks/useVoiceCommand";
import AnalyticsPanel from "../components/AnalyticsPanel";

const AGENT_LAYOUT = [
  { role: "product_manager", position: [0, 2.2, -2] },
  { role: "backend_engineer", position: [-3, 0, -1] },
  { role: "frontend_engineer", position: [3, 0, -1] },
  { role: "qa_engineer", position: [-1.8, -1.8, -1] },
  { role: "devops_engineer", position: [1.8, -1.8, -1] },
];

export default function Workspace({ projectId }) {
  const { agentActivity, taskStatuses, deploymentStatus, sendCommand } = useNexusProject(projectId);
  const [command, setCommand] = useState("");
  const [activeCode, setActiveCode] = useState("# Generated code will stream in here...");

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

    // The Web Speech API only exposes whatever synthetic voices the OS/
    // browser ships — there's no literal "roar"/growl effect available,
    // only voice selection plus pitch/rate tuning. This picks the
    // deepest-sounding male system voice available, in priority order
    // of ones known to sound notably deep/authoritative, falling back
    // to any voice whose name suggests "male" if none of those exist,
    // and finally to the browser default if the OS exposes no gender
    // hints at all (varies a lot by platform).
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

      return null; // fall back to the browser's default voice
    };

    const speakNext = () => {
      if (cancelled || index >= lines.length) return;
      const utterance = new SpeechSynthesisUtterance(lines[index]);
      const voice = pickDeepMaleVoice();
      if (voice) utterance.voice = voice;
      // Lower pitch + slightly slower rate = the closest a synthetic
      // voice can get to a deep, commanding delivery. Pitch below
      // ~0.6 starts sounding distorted/robotic on most engines rather
      // than genuinely deeper, so this stays just above that floor.
      utterance.pitch = 0.65;
      utterance.rate = 0.92;
      utterance.onend = () => {
        if (cancelled) return;
        index++;
        setTimeout(speakNext, 500);
      };
      window.speechSynthesis.speak(utterance);
    };

    // React.StrictMode (see main.jsx) intentionally mounts every
    // component twice in development — mount, cleanup, mount again —
    // to surface missing-cleanup bugs. The throwaway first mount used
    // to call speak() immediately, and speechSynthesis.cancel() in
    // cleanup doesn't reliably silence audio that's already started in
    // time, so that phantom first mount was often audible before the
    // real mount's greeting started right after it — which is exactly
    // why "Welcome back" was heard twice. Deferring the actual speak()
    // call by one tick means the throwaway mount's cleanup (which sets
    // `cancelled = true` and clears the timer) always wins the race,
    // so only the mount that actually survives ever produces sound.
    // This delay is imperceptible and only matters in development —
    // StrictMode's double-invoke doesn't happen in production builds.
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

  // Phase 7: voice fills the same input a typed command would, then
  // submits automatically — backend has no separate voice code path.
  const { start: startListening, listening, supported: voiceSupported } = useVoiceCommand((transcript) => {
    setCommand(transcript);
    sendCommand(transcript);
  });

  const activeRoles = new Set(
    Object.values(taskStatuses)
      .filter((t) => t.status === "in_progress")
      .map((t) => t.role)
  );

  const latestCodeStream = [...agentActivity].reverse().find((a) => a.message_type === "code");
  if (latestCodeStream && latestCodeStream.content !== activeCode) {
    // cheap live-update; a production version would diff/stream token-by-token
  }

  return (
    <div
      style={{
        position: "relative",
        width: "100vw",
        height: "100dvh",
        background: "#05060a",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* 3D scene + floating panels — fills all space above the command bar */}
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <Canvas camera={{ position: [0, 0, 8], fov: 50 }}>
          <ambientLight intensity={0.4} />
          <pointLight position={[5, 5, 5]} intensity={1.2} color="#00d9ff" />
          <pointLight position={[-5, -5, 5]} intensity={0.8} color="#ff6b35" />
          <Stars radius={60} depth={40} count={2000} factor={3} fade />

          {AGENT_LAYOUT.map((a) => (
            <AgentNode key={a.role} role={a.role} position={a.position} active={activeRoles.has(a.role)} />
          ))}

          <OrbitControls enablePan={false} minDistance={4} maxDistance={14} />
        </Canvas>

        {/* Analytics panel — floats top-left over the canvas only */}
        <div style={{ position: "absolute", top: 12, left: 12, zIndex: 2, maxWidth: "calc(100vw - 24px)" }}>
          <AnalyticsPanel projectId={projectId} deploymentStatus={deploymentStatus} />
        </div>

        {/* Code editor — floats top-right over the canvas only, shrinks on mobile */}
        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            zIndex: 2,
            width: "min(380px, 44vw)",
            height: "min(260px, 32vh)",
            minWidth: 160,
            borderRadius: 12,
            overflow: "hidden",
            border: "1px solid #00d9ff44",
            boxShadow: "0 0 40px #00d9ff22",
          }}
        >
          <Editor
            height="100%"
            theme="vs-dark"
            defaultLanguage="python"
            value={latestCodeStream?.content ?? activeCode}
            options={{ readOnly: true, fontSize: 11, minimap: { enabled: false } }}
          />
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
          background: "#0a0d14ee",
          borderTop: "1px solid #00d9ff33",
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
            borderRadius: 8,
            border: "1px solid #00d9ff66",
            background: "#0a0d14cc",
            color: "#e6faff",
            fontFamily: "monospace",
            fontSize: 14,
          }}
        />
        {voiceSupported && (
          <button
            type="button"
            onClick={startListening}
            title="Voice command"
            style={{
              flexShrink: 0,
              padding: "12px 14px",
              borderRadius: 8,
              border: `1px solid ${listening ? "#ff6b35" : "#00d9ff66"}`,
              background: listening ? "#ff6b3522" : "#0a0d14cc",
              color: listening ? "#ff6b35" : "#00d9ff",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            {listening ? "●" : "🎙"}
          </button>
        )}
        <button
          type="submit"
          style={{
            flexShrink: 0,
            padding: "12px 18px",
            borderRadius: 8,
            border: "none",
            background: "#00d9ff",
            color: "#05060a",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Build →
        </button>
      </form>
    </div>
  );
}
