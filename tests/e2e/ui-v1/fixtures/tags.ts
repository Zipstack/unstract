/**
 * Distribution tags. Every spec carries at least one: the config only runs
 * tests tagged for the current distribution, so an untagged spec never runs.
 * This repo's `frontend-v1-e2e` runs `@oss`; unstract-cloud's
 * `frontend-v1-e2e-cloud` runs `@cloud` over the same folder. Cloud-only pages
 * belong in unstract-cloud (`specs/cloud/`), not here.
 *
 *   test("…", { tag: DIST.both }, async () => {});
 *   test.describe("…", { tag: DIST.cloud }, () => {});
 */

import type { Distribution } from "../contract/registry.ts";

export const TAG = {
  oss: "@oss",
  cloud: "@cloud",
  onprem: "@onprem",
} as const;

type Tag = (typeof TAG)[keyof typeof TAG];

// Mutable arrays: Playwright's `tag` option does not accept readonly ones.
export const DIST: Readonly<
  Record<"oss" | "cloud" | "onprem" | "both" | "all", Tag[]>
> = {
  oss: [TAG.oss],
  cloud: [TAG.cloud],
  onprem: [TAG.onprem],
  /** OSS and cloud: the usual case for a Document Studio page. */
  both: [TAG.oss, TAG.cloud],
  all: [TAG.oss, TAG.cloud, TAG.onprem],
};

const DISTRIBUTIONS: readonly Distribution[] = ["oss", "cloud", "onprem"];

/** UNSTRACT_DISTRIBUTION picks the set; OSS is this repo's default. */
export function currentDistribution(): Distribution {
  const raw = process.env.UNSTRACT_DISTRIBUTION?.toLowerCase() ?? "oss";
  if (!DISTRIBUTIONS.includes(raw as Distribution)) {
    throw new Error(
      `UNSTRACT_DISTRIBUTION=${raw} is not one of ${DISTRIBUTIONS.join(", ")}`,
    );
  }
  return raw as Distribution;
}

/** The `grep` the config applies: tests tagged for this distribution only. */
export function distributionGrep(): RegExp {
  return new RegExp(String.raw`${TAG[currentDistribution()]}\b`);
}
