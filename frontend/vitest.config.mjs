import fs from "node:fs";
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

/*
 * Mirror of optionalPluginImports() in vite.config.js — the same asymmetry the
 * note above warns about, in a second place.
 *
 * `src/helpers/GetStaticData.js` does `try { await import("../plugins/...") }`,
 * which the build resolves to an empty module when the cloud plugin tree is
 * absent. Vitest does not read vite.config.js, so in the OSS-only checkout any
 * test importing a component that reaches GetStaticData failed to COLLECT —
 * reported as a failed file, not a failed assertion, and easy to read as
 * unrelated infrastructure noise.
 */
function optionalPluginImports() {
  return {
    name: "optional-plugin-imports",
    resolveId(source, importer) {
      if (!importer || !source.startsWith(".")) {
        return null;
      }
      const sourcePath = source.split("?")[0].split("#")[0];
      const resolved = path.resolve(path.dirname(importer), sourcePath);
      if (!resolved.includes("/plugins/")) {
        return null;
      }
      const exists = ["", ".js", ".jsx", ".ts", ".tsx"].some(
        (ext) =>
          fs.existsSync(resolved + ext) ||
          fs.existsSync(path.join(resolved, `index${ext || ".js"}`)),
      );
      return exists ? null : `\0optional-plugin:${resolved}`;
    },
    load(id) {
      return id.startsWith("\0optional-plugin:") ? "export default {};" : null;
    },
  };
}

export default defineConfig({
  plugins: [
    // Must precede react(), as in vite.config.js.
    jsxInJs(),
    optionalPluginImports(),
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
    /*
     * The Playwright suite (the rig's `ui` group) lives in `tests/e2e/ui`, out
     * of this tree entirely, so vitest's default glob no longer reaches it.
     * `build/` is listed because a production build lands there and its
     * bundled chunks would otherwise be walked.
     */
    exclude: ["**/node_modules/**", "**/dist/**", "**/build/**"],
  },
});
