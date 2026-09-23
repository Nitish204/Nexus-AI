import { describe, expect, it } from "vitest";
import { defaultProjectName } from "./projectNaming";

describe("defaultProjectName", () => {
  it("returns a string starting with the expected prefix", () => {
    const name = defaultProjectName();
    expect(name.startsWith("Project — ")).toBe(true);
  });

  it("embeds today's month/day so two projects created on different days differ", () => {
    const name = defaultProjectName();
    const expectedDate = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric" });
    expect(name).toContain(expectedDate);
  });

  it("produces a non-empty, single-line name suitable for a sidebar label", () => {
    const name = defaultProjectName();
    expect(name.length).toBeGreaterThan(0);
    expect(name).not.toContain("\n");
  });
});
