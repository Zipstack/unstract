import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react({
      include: "**/*.{jsx,js}",
    }),
  ],
  esbuild: {
    loader: "jsx",
    include: /src\/.*\.jsx?$/,
  },
  // P0-14: the `@` alias exists in vite.config.js but was missing here, so the
  // first test importing `@/components/ui/*` would fail to resolve.
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "happy-dom",
    setupFiles: "./src/setupTests.js",
    // Tailwind v4's `@import "tailwindcss"` / `@plugin` at-rules are not
    // processable by vitest's CSS pipeline; stub CSS imports in tests.
    css: false,
  },
});
