import { useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars, Html } from "@react-three/drei";
import Editor from "@monaco-editor/react";
import AgentNode from "./AgentNode";
import { useNexusProject } from "../hooks/useNexusProject";
import { useVoiceCommand } from "../hooks/useVoiceCommand";
import AnalyticsPanel from "../components/AnalyticsPanel";
import { useState } from "react";

useEffect(() => {
  const lines = [
    "Welcome back.",
    "Nexus is online.",
    "Your intelligent engineering workspace has been fully initialized.",
    "Project management, architecture, frontend, backend, quality assurance, and DevOps specialists are standing by.",
    "Share your vision.",
    "And let's build something extraordinary."
  ];

  let index = 0;

  const speakNext = () => {
    if (index >= lines.length) return;

    const utterance = new SpeechSynthesisUtterance(lines[index]);
    utterance.rate = 1;
    utterance.pitch = 1;

    utterance.onend = () => {
      index++;
      setTimeout(speakNext, 500); // 0.5-second pause
    };

    window.speechSynthesis.speak(utterance);
  };

  speakNext();

  return () => {
    window.speechSynthesis.cancel();
  };
}, []);

  // Some browsers load voices asynchronously — wait if needed
  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.onvoiceschanged = greet;
  } else {
    greet();
  }

  return () => window.speechSynthesis.cancel();
}, []);

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
    <div style={{ position: "relative", width: "100vw", height: "100vh", background: "#05060a" }}>
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

      <AnalyticsPanel projectId={projectId} deploymentStatus={deploymentStatus} />

      {/* Floating code editor panel — overlaid via CSS, not R3F Html, for
          crisp text rendering (Monaco doesn't render well through WebGL) */}
      <div
        style={{
          position: "absolute",
          top: 24,
          right: 24,
          width: 420,
          height: 320,
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
          options={{ readOnly: true, fontSize: 12, minimap: { enabled: false } }}
        />
      </div>

      {/* Command input — this is where typed OR voice-transcribed text lands */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!command.trim()) return;
          sendCommand(command);
          setCommand("");
        }}
        style={{
          position: "absolute",
          bottom: 24,
          left: "50%",
          transform: "translateX(-50%)",
          width: "60%",
          display: "flex",
          gap: 8,
        }}
      >
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder='e.g. "Build a Django authentication system with JWT and PostgreSQL"'
          style={{
            flex: 1,
            padding: "12px 16px",
            borderRadius: 8,
            border: "1px solid #00d9ff66",
            background: "#0a0d14cc",
            color: "#e6faff",
            fontFamily: "monospace",
          }}
        />
        {voiceSupported && (
          <button
            type="button"
            onClick={startListening}
            title="Voice command"
            style={{
              padding: "12px 16px",
              borderRadius: 8,
              border: `1px solid ${listening ? "#ff6b35" : "#00d9ff66"}`,
              background: listening ? "#ff6b3522" : "#0a0d14cc",
              color: listening ? "#ff6b35" : "#00d9ff",
              cursor: "pointer",
              fontWeight: 700,
            }}
          >
            {listening ? "● Listening..." : "🎙"}
          </button>
        )}
        <button
          type="submit"
          style={{
            padding: "12px 20px",
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
