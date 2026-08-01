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
    const token = localStorage.getItem("nexus_token");
    const ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}?token=${encodeURIComponent(token || "")}`);
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

  const authHeaders = () => {
    const token = localStorage.getItem("nexus_token");
    return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
  };

  const sendCommand = useCallback(
    async (text) => {
      console.log("[NEXUS] sendCommand called with:", text, "projectId:", projectId);
      try {
        const res = await fetch(`${API_BASE}/api/projects/${projectId}/command`, {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ text }),
        });
        const data = await res.json().catch(() => null);
        console.log("[NEXUS] sendCommand response:", res.status, data);
        if (!res.ok) {
          console.error("[NEXUS] sendCommand FAILED with status", res.status, data);
        }
      } catch (err) {
        console.error("[NEXUS] sendCommand THREW an exception before/during fetch:", err);
      }
    },
    [projectId]
  );

  const refreshFiles = useCallback(async () => {
    const res = await fetch(`${API_BASE}/api/projects/${projectId}/files`, {
      headers: authHeaders(),
    });
    const data = await res.json();
    const byPath = Object.fromEntries(data.map((f) => [f.path, f]));
    setFiles(byPath);
  }, [projectId]);

  return { agentActivity, taskStatuses, files, deploymentStatus, sandboxResults, sendCommand, refreshFiles };
}
