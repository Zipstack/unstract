import path from "node:path";
import react from "@vitejs/plugin-react";
import { transformWithEsbuild } from "vite";
import { defineConfig } from "vitest/config";

/*
 * Mirror of jsxInJs() in vite.config.js — see the long note there.
 *
 * Kept here even though no OSS `.js` file currently contains JSX: the cloud
 * plugin tree (copied into src/plugins/ at Docker build time) has nine that
 * do, and this config must be able to load them. Vitest does not read
 * vite.config.js, so anything fixed only there is missing here — that
 * asymmetry once left the suite silently loading 126 of 248 tests while
 * still reporting all green.
 */
function jsxInJs() {
  return {
    name: "jsx-in-js",
    async transform(code, id) {
      if (id.includes("/node_modules/")) {
        return null;
      }
      const [filepath] = id.split("?");
      if (!/\/src\/.*\.js$/.test(filepath)) {
        return null;
      }
      // jsx: "automatic" — see the note in vite.config.js. Without it esbuild
      // emits classic React.createElement against a React these files never
      // import, which throws at render rather than failing the build.
      return transformWithEsbuild(code, filepath, {
        loader: "jsx",
        jsx: "automatic",
      });
    },
  };
}

export default defineConfig({
  plugins: [
    // Must precede react(), as in vite.config.js.
    jsxInJs(),
    react({
      include: "**/*.{jsx,js,tsx,ts}",
    }),
  ],
  /*
   * No `esbuild` override — see the matching note in vite.config.js. In short:
   * `include` REPLACES Vite's default filter (so a `.jsx?`-only regex hides
   * .ts/.tsx from the transform entirely), and `loader` must be a single
   * string applied to every matched file (so "jsx" misparses TypeScript
   * generics). Vite's defaults derive the loader per file extension; JSX in
   * `.js` is handled by jsxInJs() above.
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
