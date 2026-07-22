import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { optionalPluginImports } from "./vite-plugins/optional-plugin-imports";

// Two projects, because they need different environments:
//   unit   — happy-dom, fast, but no layout engine (every rect measures 0)
//   layout — real Chromium via playwright, the only place geometry is real
// `bun run test` runs both; `test:unit` / `test:layout` run one.
export default defineConfig({
  plugins: [
    // src/plugins/** is cloud content: gitignored, absent from OSS checkouts
    // and from CI. Vite resolves those imports at transform time and fails the
    // module outright, so tests need the same treatment the production build
    // gives them — the very same plugin, not a lookalike. It makes a missing
    // plugin *throw* on import, which is the signal the runtime fallbacks in
    // pluginRegistry and friends match on; stubbing it to an empty module
    // instead would make every one of those fallbacks silently take the wrong
    // branch under test.
    optionalPluginImports(),
    react({
      include: "**/*.{jsx,js}",
    }),
  ],
  esbuild: {
    loader: "jsx",
    include: /src\/.*\.jsx?$/,
  },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          globals: true,
          environment: "happy-dom",
          setupFiles: "./src/setupTests.js",
          include: ["src/**/*.test.{js,jsx}"],
          // Layout specs need a browser; they are the other project.
          exclude: ["src/**/*.layout.test.{js,jsx}"],
        },
      },
      {
        extends: true,
        test: {
          name: "layout",
          globals: true,
          include: ["src/**/*.layout.test.{js,jsx}"],
          setupFiles: "./src/test-utils/layout/setup.js",
          browser: {
            enabled: true,
            provider: "playwright",
            headless: true,
            screenshotFailures: true,
            instances: [
              {
                browser: "chromium",
                // Fixed so a runner's default window size can never change
                // what is measured. Cases size the list themselves; this only
                // has to be wider than the widest case.
                viewport: { width: 1600, height: 900 },
              },
            ],
          },
        },
      },
    ],
  },
});
