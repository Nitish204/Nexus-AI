import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    // jsdom (not "node"): components/hooks under test touch window,
    // document.cookie, navigator.serviceWorker, etc.
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
    globals: true,
    css: false,
  },
});
