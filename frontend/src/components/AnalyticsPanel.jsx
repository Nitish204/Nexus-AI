import { useState, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

function authHeaders() {
  const token = localStorage.getItem("nexus_token");
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

function StatRow({ label, value, valueColor }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "3px 0" }}>
      <span style={{ color: "#8fd9ec99", fontSize: 11 }}>{label}</span>
      <span style={{ color: valueColor || "#e6faff", fontSize: 13, fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export default function AnalyticsPanel({ projectId, deploymentStatus }) {
  const [analysis, setAnalysis] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [latestDeployment, setLatestDeployment] = useState(null);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/analytics/run`, {
        method: "POST",
        headers: authHeaders(),
      });
      setAnalysis(await res.json());
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const pollDeployment = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/deployment`, {
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data) setLatestDeployment(data);
    } catch {
      // ignore transient errors while polling
    }
  }, [projectId]);

  const deploy = useCallback(async () => {
    setDeploying(true);
    try {
      await fetch(`${API_BASE}/api/projects/${projectId}/deploy`, {
        method: "POST",
        headers: authHeaders(),
      });
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
  const deployColor =
    shownDeployment?.status === "live" ? "#39ff88" : shownDeployment?.status === "failed" ? "#ff6b35" : "#ffd23f";

  return (
    <div
      style={{
        width: "min(270px, 88vw)",
        padding: "16px 16px 14px",
        borderRadius: 14,
        background: "linear-gradient(165deg, #0d1119ee, #0a0d14e6)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
        border: "1px solid #ffffff14",
        boxShadow: "0 8px 32px #00000066, 0 0 0 1px #39ff8814, 0 0 24px #39ff8811",
        color: "#e6faff",
        fontFamily: "monospace",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#39ff88", boxShadow: "0 0 8px #39ff88" }} />
          <strong style={{ color: "#39ff88", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
            Analytics
          </strong>
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading}
          style={{
            background: "#39ff8814",
            border: "1px solid #39ff8855",
            color: "#39ff88",
            borderRadius: 7,
            padding: "5px 10px",
            fontSize: 11,
            fontWeight: 600,
            cursor: loading ? "default" : "pointer",
            fontFamily: "monospace",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => !loading && (e.currentTarget.style.background = "#39ff8828")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#39ff8814")}
        >
          {loading ? "Scanning…" : "Scan"}
        </button>
      </div>

      <div style={{ background: "#00000022", borderRadius: 8, padding: "8px 10px", marginBottom: 12 }}>
        <StatRow label="Files scanned" value={analysis.length} />
        <StatRow label="Avg complexity" value={avgComplexity} />
        <StatRow
          label="Security issues"
          value={totalSecurityIssues}
          valueColor={totalSecurityIssues > 0 ? "#ff6b35" : "#39ff88"}
        />
      </div>

      <div style={{ height: 1, background: "linear-gradient(90deg, transparent, #ffffff22, transparent)", margin: "12px 0" }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#ffd23f", boxShadow: "0 0 8px #ffd23f" }} />
          <strong style={{ color: "#ffd23f", fontSize: 12, letterSpacing: "0.04em", textTransform: "uppercase" }}>
            Deploy
          </strong>
        </div>
        <button
          onClick={deploy}
          disabled={deploying}
          style={{
            background: "linear-gradient(135deg, #ffd23f, #ffb020)",
            border: "none",
            color: "#0a0d14",
            borderRadius: 7,
            padding: "6px 12px",
            fontSize: 11,
            fontWeight: 700,
            cursor: deploying ? "default" : "pointer",
            fontFamily: "monospace",
            boxShadow: deploying ? "none" : "0 2px 8px #ffd23f33",
            opacity: deploying ? 0.7 : 1,
          }}
        >
          {deploying ? "Deploying…" : "🚀 Deploy"}
        </button>
      </div>

      {shownDeployment && (
        <div
          style={{
            marginTop: 10,
            padding: "8px 10px",
            borderRadius: 8,
            background: "#00000022",
            border: `1px solid ${deployColor}33`,
          }}
        >
          <div style={{ color: deployColor, fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: deployColor }} />
            {shownDeployment.status}
            {shownDeployment.url ? ` → ${shownDeployment.url}` : ""}
          </div>
          {shownDeployment.log && (
            <div style={{ color: "#8fd9ec80", marginTop: 4, fontSize: 10.5, lineHeight: 1.4 }}>{shownDeployment.log}</div>
          )}
        </div>
      )}
    </div>
  );
}
