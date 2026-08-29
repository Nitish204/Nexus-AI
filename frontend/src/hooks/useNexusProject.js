import { useEffect, useRef, useState, useCallback } from "react";
import { API_BASE, apiFetch, getWsToken } from "../utils/api";

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
    // Reset all per-project state immediately when switching projects.
    // Previously this only happened implicitly (or not at all) — the
    // WebSocket reconnected correctly, but agentActivity/taskStatuses/
    // deploymentStatus/sandboxResults kept whatever was left over from
    // the PREVIOUS project, since React reuses this same hook instance
    // across a projectId prop change rather than remounting it. That's
    // exactly why switching projects showed stale code from whichever
    // project was open before.
    setAgentActivity([]);
    setTaskStatuses({});
    setDeploymentStatus(null);
    setSandboxResults([]);
    setFiles({});

    if (!projectId) return;
    let cancelled = false;
    let ws = null;

    // Load the project's ACTUAL saved files immediately on open — this
    // was completely missing before. The editor previously only ever
    // showed live WebSocket stream messages from the current session,
    // so opening an existing project with real code already generated
    // in a past session showed nothing at all until a brand-new
    // command happened to stream something.
    apiFetch(`/api/projects/${projectId}/files`)
      .then((res) => res.json())
      .then((data) => {
        const byPath = Object.fromEntries((Array.isArray(data) ? data : []).map((f) => [f.path, f]));
        setFiles(byPath);
      })
      .catch(() => setFiles({}));

    // The WebSocket needs its own short-lived token (see utils/api.js
    // for why this can't just reuse the httpOnly session cookie) —
    // fetched fresh right before each connection attempt.
    getWsToken()
      .then((token) => {
        if (cancelled) return;
        ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}?token=${encodeURIComponent(token)}`);
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
      })
      .catch((err) => console.error("[NEXUS] Couldn't open the live connection:", err));

    return () => {
      cancelled = true;
      if (ws) ws.close();
    };
  }, [projectId]);

  const sendCommand = useCallback(
    async (text) => {
      console.log("[NEXUS] sendCommand called with:", text, "projectId:", projectId);
      try {
        const res = await apiFetch(`/api/projects/${projectId}/command`, {
          method: "POST",
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
    const res = await apiFetch(`/api/projects/${projectId}/files`);
    const data = await res.json();
    const byPath = Object.fromEntries(data.map((f) => [f.path, f]));
    setFiles(byPath);
  }, [projectId]);

  return { agentActivity, taskStatuses, files, deploymentStatus, sandboxResults, sendCommand, refreshFiles };
}
