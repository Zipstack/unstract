import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    react({
      include: "**/*.{jsx,js,tsx,ts}",
    }),
  ],
  /*
   * No `esbuild` override — see the matching note in vite.config.js. In short:
   * `include` REPLACES Vite's default filter (so a `.jsx?`-only regex hides
   * .ts/.tsx from the transform entirely), and `loader` must be a single
   * string applied to every matched file (so "jsx" misparses TypeScript
   * generics). Vite's defaults derive the loader per file extension, which is
   * correct for every file here now that no .js file contains JSX.
   *
   * This must stay in sync with vite.config.js: Vitest does not read that
   * file, so a transform fixed only there leaves the tests failing to load.
   */
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
