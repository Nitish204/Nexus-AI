import Workspace from "./scenes/Workspace";

// Swap for a real project picker later — hardcoded here so the loop
// (create project via API -> paste ID -> watch it build) is testable
// on day one.
const DEMO_PROJECT_ID = new URLSearchParams(window.location.search).get("project") ?? "";

export default function App() {
  if (!DEMO_PROJECT_ID) {
    return (
      <div style={{ color: "#e6faff", fontFamily: "monospace", padding: 40, background: "#05060a", height: "100vh" }}>
        <h2>NEXUS</h2>
        <p>Create a project via <code>POST /api/projects</code>, then open:</p>
        <code>?project=&lt;project_id&gt;</code>
      </div>
    );
  }
  return <Workspace projectId={DEMO_PROJECT_ID} />;
}
