import path from "node:path";
import { defineV1Config } from "../../vitest.v1.config.mts";

/*
 * The real v1 config, coverage threshold included, rooted at one case in
 * ./cases (named by V1_GATE_CASE), whose own src/v1 tree stands in for the
 * real one. Only the setup file is re-pointed, at the real harness, and the
 * report and Vite's cache go to V1_GATE_REPORTS so a run never writes into
 * the tree. Used only by unit-gate.fixtures.mjs.
 */
const FRONTEND = path.resolve(import.meta.dirname, "..", "..");
const CASE = process.env.V1_GATE_CASE ?? "";
const REPORTS = process.env.V1_GATE_REPORTS ?? "";
if (!CASE || !REPORTS) {
  throw new Error("Set V1_GATE_CASE and V1_GATE_REPORTS");
}
const base = defineV1Config("core");

export default {
  ...base,
  root: path.join(import.meta.dirname, "cases", CASE),
  cacheDir: path.join(REPORTS, "vite"),
  test: {
    ...base.test,
    setupFiles: [path.join(FRONTEND, "src", "v1", "test", "setup.ts")],
    coverage: { ...base.test?.coverage, reportsDirectory: REPORTS },
  },
};
