import svgr from "vite-plugin-svgr";
import { defineConfig } from "vitest/config";
import v0 from "./vitest.config.mjs";

/*
 * Vitest config for the v1 frontend (src/v1), run by the rig's
 * `frontend-v1-unit` group and by `bun run test:v1`. The v0 config excludes
 * src/v1, so the two suites never share a run, a result or a coverage report.
 *
 * A separate file rather than Vitest `projects`: coverage is root-level in
 * projects mode, so v1 could not have its own report directory or threshold.
 *
 * Plugins and aliases are taken from the v0 config field by field rather than
 * with mergeConfig, which would concatenate v0's `exclude` (which now holds
 * src/v1) and `setupFiles` into this one. svgr is added because v1 imports
 * SVGs as components (`@v1/assets/logo.svg?react`), as vite.config.js allows.
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
    plugins: [...(v0.plugins ?? []), svgr()],
    resolve: v0.resolve,
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
        enabled: true,
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
