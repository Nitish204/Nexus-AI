// Shared Vitest setup: extends `expect` with jest-dom matchers
// (toBeInTheDocument, etc.) for every test file automatically.
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom doesn't clear document.cookie between tests automatically, and
// assigning document.cookie = "" is a no-op (it isn't valid cookie
// syntax) — actually expiring each cookie is required.
function clearAllCookies() {
  document.cookie.split(";").forEach((c) => {
    const name = c.split("=")[0].trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
}

afterEach(() => {
  cleanup();
  clearAllCookies();
});
