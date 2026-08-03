/**
 * Generates a distinguishing default name for a newly created project,
 * e.g. "Project — Aug 2, 2:44 PM". Previously every project was
 * hardcoded to the literal string "New Project" with no way to tell
 * them apart in the sidebar.
 */
export function defaultProjectName() {
  const now = new Date();
  const date = now.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const time = now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `Project — ${date}, ${time}`;
}
