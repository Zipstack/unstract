/**
 * Entry point for every v1 spec:
 *
 *   import { DIST, expect, test } from "../fixtures/index.ts";
 *
 * `test` carries the login (`session`, `app`, `role`), `seed` and
 * `v1Preview` fixtures.
 */

export { expect } from "@playwright/test";
export type { App, Role, Session } from "./auth.ts";
export { enableV1Preview, test } from "./preview.ts";
export type { CreateOptions, Seed } from "./seed.ts";
export { currentDistribution, DIST, TAG } from "./tags.ts";
