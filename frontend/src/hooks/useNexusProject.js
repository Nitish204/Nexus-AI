import { useEffect, useRef, useState, useCallback } from "react";

// Point this at your deployed backend. Using env var so it can differ
// between local dev and production (Netlify) builds.
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

/**
 * Connects the 3D workspace to the Python backend: opens the WebSocket
 * for live agent activity and exposes a `sendCommand` function that
 * kicks off the orchestrator (typed or voice-transcribed text).
 */
export function useNexusProject(projectId) {
  const [agentActivity, setAgentActivity] = useState([]);
  const [taskStatuses, setTaskStatuses] = useState({});
  const [files, setFiles] = useState({});
  const [deploymentStatus, setDeploymentStatus] = useState(null);
  const [sandboxResults, setSandboxResults] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    if (!projectId) return;
    const ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}`);
    wsRef.current = ws;
    ws.onmessage = (event) => {
      const { type, payload } = JSON.parse(event.data);
      if (type === "agent_message" || type === "agent_stream") {
        setAgentActivity((prev) => [...prev.slice(-199), { type, ...payload, t: Date.now() }]);
      }
      if (type === "task_status") {
        setTaskStatuses((prev) => ({ ...prev, [payload.task_id]: payload }));
      }
      if (type === "deployment_status") {
        setDeploymentStatus(payload);
      }
      if (type === "sandbox_result") {
        setSandboxResults((prev) => [...prev.slice(-49), payload]);
      }
    };
    return () => ws.close();
  }, [projectId]);

  const sendCommand = useCallback(
    async (text) => {
      await fetch(`${API_BASE}/api/projects/${projectId}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    },
    [projectId]
  );

  const refreshFiles = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/files`);
    const data = await res.json();
    const byPath = Object.fromEntries(data.map((f) => [f.path, f]));
    setFiles(byPath);
  }, [projectId]);

  return { agentActivity, taskStatuses, files, deploymentStatus, sandboxResults, sendCommand, refreshFiles };
}
