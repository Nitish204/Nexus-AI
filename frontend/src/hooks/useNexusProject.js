import { useEffect, useRef, useState, useCallback } from "react";
import { API_BASE, BACKEND_WS_ORIGIN, apiFetch, getWsToken } from "../utils/api";

const WS_BASE = BACKEND_WS_ORIGIN;

// Backoff schedule for WebSocket reconnection: fast first retry (a
// dropped connection is often transient), then backs off so a real
// outage doesn't hammer the server with reconnect attempts every second.
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000, 10000];

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
  // Bug fix: there was previously no way for the UI to know the
  // WebSocket had dropped — the "live" workspace would go silently
  // dark on any network blip, server restart, or the free-tier Render
  // backend idling out, with no reconnect attempt and no user-visible
  // signal that anything was wrong. connectionStatus now surfaces
  // "connecting" | "open" | "reconnecting" | "closed" so the UI can
  // show a real status indicator instead of implying everything is
  // fine while agent updates have actually stopped arriving.
  const [connectionStatus, setConnectionStatus] = useState("connecting");
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
    setConnectionStatus("connecting");

    if (!projectId) return;
    let cancelled = false;
    let ws = null;
    let reconnectAttempt = 0;
    let reconnectTimer = null;

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

    function connect() {
      // The WebSocket needs its own short-lived token (see utils/api.js
      // for why this can't just reuse the httpOnly session cookie) —
      // fetched fresh right before each connection attempt, including
      // every reconnect, since a stale token would just fail again.
      getWsToken()
        .then((token) => {
          if (cancelled) return;
          ws = new WebSocket(`${WS_BASE}/ws/projects/${projectId}?token=${encodeURIComponent(token)}`);
          wsRef.current = ws;

          ws.onopen = () => {
            reconnectAttempt = 0;
            setConnectionStatus("open");
          };

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

          ws.onclose = () => {
            if (cancelled) return;
            const delay = RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
            reconnectAttempt += 1;
            setConnectionStatus("reconnecting");
            reconnectTimer = setTimeout(connect, delay);
          };

          ws.onerror = () => {
            // onclose fires right after onerror for a failed connection,
            // so the reconnect scheduling above already covers this —
            // this handler just avoids an unhandled error bubbling up.
          };
        })
        .catch((err) => {
          console.error("[NEXUS] Couldn't open the live connection:", err);
          if (cancelled) return;
          const delay = RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
          reconnectAttempt += 1;
          setConnectionStatus("reconnecting");
          reconnectTimer = setTimeout(connect, delay);
        });
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, [projectId]);

  const sendCommand = useCallback(
    async (text) => {
      try {
        const res = await apiFetch(`/api/projects/${projectId}/command`, {
          method: "POST",
          body: JSON.stringify({ text }),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) {
          console.error("[NEXUS] sendCommand failed:", res.status, data);
          throw new Error(data?.detail || "Couldn't send that command — please try again.");
        }
        return data;
      } catch (err) {
        console.error("[NEXUS] sendCommand error:", err);
        throw err;
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

  return {
    agentActivity,
    taskStatuses,
    files,
    deploymentStatus,
    sandboxResults,
    connectionStatus,
    sendCommand,
    refreshFiles,
  };
}
