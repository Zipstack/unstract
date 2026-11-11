/**
 * Distribution tags. Every test carries at least one: a test tagged for
 * another distribution is skipped, and one with no distribution tag fails.
 * This repo's `frontend-v1-e2e` runs `@oss`; unstract-cloud's
 * `frontend-v1-e2e-cloud` runs `@cloud` over the same folder. Cloud-only pages
 * belong in unstract-cloud (`specs/cloud/`), not here.
 *
 *   test("…", { tag: DIST.both }, async () => {});
 *   test.describe("…", { tag: DIST.cloud }, () => {});
 */

import { test as base } from "@playwright/test";
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

export type TagVerdict =
  | { kind: "run" }
  | { kind: "skip"; reason: string }
  | { kind: "fail"; reason: string };

const KNOWN: readonly string[] = Object.values(TAG);

/**
 * Whether a test with these tags runs in `distribution`. Untagged, or tagged
 * only with something that is not a distribution tag (`@OSS`, `@os`), is an
 * error: such a test would otherwise never run anywhere and stay unnoticed.
 */
export function tagVerdict(
  tags: readonly string[],
  distribution: Distribution,
): TagVerdict {
  const distributions = tags.filter((t) => KNOWN.includes(t));
  if (!distributions.length) {
    return {
      kind: "fail",
      reason: `no distribution tag (tags: ${tags.join(" ") || "none"}); add { tag: DIST.… } from fixtures/tags.ts`,
    };
  }
  if (!distributions.includes(TAG[distribution])) {
    return {
      kind: "skip",
      reason: `tagged ${distributions.join(" ")}, not for ${distribution}`,
    };
  }
  return { kind: "run" };
}

/**
 * Applies `tagVerdict` to every test, as an auto fixture rather than the
 * config's `grep`: `grep` drops a test before it is collected, so an
 * untagged one would vanish without a trace.
 */
export const test = base.extend<{ distributionGate: undefined }>({
  distributionGate: [
    // biome-ignore lint/correctness/noEmptyPattern: Playwright requires a destructured first argument.
    async ({}, use, testInfo) => {
      const verdict = tagVerdict(testInfo.tags, currentDistribution());
      if (verdict.kind === "fail") {
        throw new Error(`${testInfo.title}: ${verdict.reason}`);
      }
      if (verdict.kind === "skip") {
        test.skip(true, verdict.reason);
      }
      await use(undefined);
    },
    { auto: true },
  ],
});
