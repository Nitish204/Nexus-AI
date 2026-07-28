import { useState, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

/**
 * Floating side panel: quality/security scores (Phase 6) and a
 * one-click deploy button (Phase 5). Kept as a separate small panel
 * rather than crowding the code editor overlay.
 */
export default function AnalyticsPanel({ projectId, deploymentStatus }) {
  const [analysis, setAnalysis] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [latestDeployment, setLatestDeployment] = useState(null);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/analytics/run`, { method: "POST" });
      setAnalysis(await res.json());
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const pollDeployment = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/deployment`);
      const data = await res.json();
      if (data) setLatestDeployment(data);
    } catch {
      // ignore transient errors while polling
    }
  }, [projectId]);

  const deploy = useCallback(async () => {
    setDeploying(true);
    try {
      await fetch(`${API_BASE}/api/projects/${projectId}/deploy`, { method: "POST" });
      for (const delay of [2000, 4000, 7000, 12000]) {
        await new Promise((r) => setTimeout(r, delay));
        await pollDeployment();
      }
    } finally {
      setDeploying(false);
    }
  }, [projectId, pollDeployment]);

  const totalSecurityIssues = analysis.reduce((sum, a) => sum + a.security_issues, 0);
  const avgComplexity = analysis.length
    ? (analysis.reduce((sum, a) => sum + a.complexity_score, 0) / analysis.length).toFixed(1)
    : "—";

  const shownDeployment = deploymentStatus || latestDeployment;

  return (
    <div
      style={{
        width: "min(260px, 88vw)",
        padding: 16,
        borderRadius: 12,
        background: "#0a0d14cc",
        border: "1px solid #39ff8844",
        boxShadow: "0 0 40px #39ff8822",
        color: "#e6faff",
        fontFamily: "monospace",
        fontSize: 12,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <strong style={{ color: "#39ff88" }}>Analytics</strong>
        <button
          onClick={runAnalysis}
          disabled={loading}
          style={{ background: "none", border: "1px solid #39ff8866", color: "#39ff88", borderRadius: 6, padding: "4px 8px", cursor: "pointer" }}
        >
          {loading ? "Scanning..." : "Scan"}
        </button>
      </div>
      <div>Files scanned: {analysis.length}</div>
      <div>Avg complexity: {avgComplexity}</div>
      <div style={{ color: totalSecurityIssues > 0 ? "#ff6b35" : "#39ff88" }}>
        Security issues: {totalSecurityIssues}
      </div>
      <hr style={{ border: "none", borderTop: "1px solid #ffffff22", margin: "12px 0" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong style={{ color: "#ffd23f" }}>Deploy</strong>
        <button
          onClick={deploy}
          disabled={deploying}
          style={{ background: "#ffd23f", border: "none", color: "#05060a", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontWeight: 700 }}
        >
          {deploying ? "Deploying..." : "🚀 Deploy"}
        </button>
      </div>
      {shownDeployment && (
        <div style={{ marginTop: 6, color: shownDeployment.status === "live" ? "#39ff88" : shownDeployment.status === "failed" ? "#ff6b35" : "#ffd23f" }}>
          {shownDeployment.status} {shownDeployment.url ? `→ ${shownDeployment.url}` : ""}
          {shownDeployment.log && (
            <div style={{ color: "#888", marginTop: 4, fontSize: 11 }}>{shownDeployment.log}</div>
          )}
        </div>
      )}
    </div>
  );
}
