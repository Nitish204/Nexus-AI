import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import Sidebar from "./Sidebar";

vi.mock("../utils/api", () => ({
  apiFetch: vi.fn(),
}));
vi.mock("../utils/push", () => ({
  isPushSupported: () => false,
  getPushSubscriptionStatus: vi.fn().mockResolvedValue("not-subscribed"),
  subscribeToPush: vi.fn(),
  unsubscribeFromPush: vi.fn(),
}));

import { apiFetch } from "../utils/api";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: async () => body });
}

describe("Sidebar", () => {
  beforeEach(() => {
    apiFetch.mockReset();
  });

  it("shows a loading state, then renders fetched projects grouped by day", async () => {
    const now = new Date().toISOString();
    apiFetch.mockReturnValue(
      jsonResponse([{ id: "p1", name: "My Project", updated_at: now, created_at: now }])
    );

    render(<Sidebar user={{ name: "Ada", email: "ada@example.com" }} currentProjectId="p1" onSelectProject={() => {}} onLogout={() => {}} />);

    expect(screen.getByText(/loading projects/i)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("My Project")).toBeInTheDocument());
    expect(apiFetch).toHaveBeenCalledWith("/api/projects");
  });

  it("shows an empty state when the user has no projects yet", async () => {
    apiFetch.mockReturnValue(jsonResponse([]));

    render(<Sidebar user={{ name: "Ada", email: "ada@example.com" }} currentProjectId="" onSelectProject={() => {}} onLogout={() => {}} />);

    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeInTheDocument());
  });

  it("falls back to an empty project list if the fetch itself throws", async () => {
    apiFetch.mockReturnValue(Promise.reject(new Error("network down")));

    render(<Sidebar user={{ name: "Ada", email: "ada@example.com" }} currentProjectId="" onSelectProject={() => {}} onLogout={() => {}} />);

    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeInTheDocument());
  });
});
