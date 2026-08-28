import AsyncStorage from "@react-native-async-storage/async-storage";

// Point this at your deployed NEXUS backend (same one the web app uses).
export const API_BASE = "https://nexus-ai-wqx2.onrender.com";

async function authHeaders() {
  const token = await AsyncStorage.getItem("nexus_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Login failed.");
  await AsyncStorage.setItem("nexus_token", data.access_token);
  return data;
}

export async function listProjects() {
  const res = await fetch(`${API_BASE}/api/projects`, { headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to load projects.");
  return res.json();
}

export async function getProjectTasks(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/tasks`, { headers: await authHeaders() });
  if (!res.ok) throw new Error("Failed to load tasks.");
  return res.json();
}

export async function triggerDeploy(projectId) {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/deploy`, {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to trigger deploy.");
  return res.json();
}
