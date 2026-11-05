import path from "node:path";
import { defineV1Config } from "../../vitest.v1.config.mts";

/*
 * The real v1 config (same setup file, same harness), pointed at the
 * known-bad cases in ./cases instead of src/v1. Used only by
 * harness.fixtures.mjs; coverage is off because it measures nothing here.
 */
const base = defineV1Config("core");

export default {
  ...base,
  root: path.resolve(import.meta.dirname, "..", ".."),
  test: {
    ...base.test,
    include: ["test-fixtures/v1-harness/cases/*.test.{ts,tsx}"],
    coverage: { enabled: false },
  },
};
