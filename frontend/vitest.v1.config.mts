import path from "node:path";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import { defineConfig } from "vitest/config";

/*
 * Vitest config for the v1 frontend (src/v1), run by the rig's
 * `frontend-v1-unit` group and by `bun run test:v1`. The v0 config excludes
 * src/v1, so the two suites never share a run, a result or a coverage report.
 *
 * A separate file rather than Vitest `projects`: coverage is root-level in
 * projects mode, so v1 could not have its own report directory or threshold.
 *
 * Deliberately NOT built from vitest.config.mjs. v0's jsxInJs() serves .js
 * files v1 may not contain, and its optionalPluginImports() stubs any missing
 * import under a `/plugins/` path, while in v1 a missing module is a bug
 * (UN-4286). Only `@v1` is aliased, so an `@/` import fails here as it does
 * in typecheck:v1. svgr serves `@v1/assets/*.svg?react`, as in vite.config.js.
 */

type Scope = "core" | "plugins";

const V1_ROOT = "src/v1";
const PLUGINS_ROOT = `${V1_ROOT}/plugins`;

type ScopeSpec = {
  root: string;
  name: string;
  reports: string;
  covers: string;
};

const SCOPES: Record<Scope, ScopeSpec> = {
  // Everything under src/v1 except plugins/, which the cloud overlay fills.
  core: {
    root: V1_ROOT,
    name: "frontend-v1",
    reports: "coverage/v1",
    covers: `${V1_ROOT}/**/*.{ts,tsx}`,
  },
  // Cloud v1 plugins only (`frontend-v1-unit-cloud`), so a cloud plugin
  // failure never reddens the OSS group. Coverage counts the plugin folders
  // (plugins/<id>/), not OSS's placeholder plugins/manifest.ts, which no
  // plugin test exercises.
  plugins: {
    root: PLUGINS_ROOT,
    name: "frontend-v1-plugins",
    reports: "coverage/v1-plugins",
    covers: `${PLUGINS_ROOT}/*/**/*.{ts,tsx}`,
  },
};

// Ratchet upward as v1 grows; see src/v1/test/README.md.
const COVERAGE_THRESHOLDS = {
  lines: 80,
  statements: 80,
  functions: 80,
  branches: 80,
};

export function defineV1Config(scope: Scope) {
  const { root, name, reports, covers } = SCOPES[scope];
  const scopeExclude = scope === "core" ? [`${PLUGINS_ROOT}/**`] : [];
  return defineConfig({
    plugins: [react(), svgr()],
    resolve: {
      alias: { "@v1": path.resolve(import.meta.dirname, V1_ROOT) },
    },
    test: {
      name,
      environment: "happy-dom",
      // Explicit `import { it, expect } from "vitest"`: the v1 tsconfig has no
      // vitest globals, so a global would type-check nowhere.
      globals: false,
      css: false,
      setupFiles: [`./${V1_ROOT}/test/setup.ts`],
      include: [`${root}/**/*.{test,spec}.{ts,tsx}`],
      exclude: ["**/node_modules/**", ...scopeExclude],
      // OSS has no plugin tests, and v1 is young; an empty run is not a failure.
      passWithNoTests: true,
      unstubGlobals: true,
      unstubEnvs: true,
      restoreMocks: true,
      coverage: {
        // The threshold is global, so a focused run (one file, one folder)
        // would fail it however its tests do. Measured only for whole-suite
        // runs: CI (the rig and every workflow set CI) and `bun run test:v1`,
        // which passes --coverage. Locally, add --coverage to measure.
        enabled: Boolean(process.env.CI),
        provider: "v8",
        reportsDirectory: reports,
        reporter: ["text-summary", "json-summary", "lcov"],
        reportOnFailure: true,
        include: [covers],
        exclude: [
          ...scopeExclude,
          `${V1_ROOT}/test/**`,
          "**/*.{test,spec}.{ts,tsx}",
          "**/*.d.ts",
        ],
        thresholds: COVERAGE_THRESHOLDS,
      },
    },
  });
}

export default defineV1Config("core");
