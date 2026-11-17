/**
 * Distribution tags. Every test carries at least one: a test tagged only for
 * another distribution is not collected (the config's grepInvert), and one
 * with no distribution tag fails (the gate below). This repo's
 * `frontend-v1-e2e` runs `@oss`; unstract-cloud's `frontend-v1-e2e-cloud`
 * runs `@cloud` over the same folder. Cloud-only pages belong in
 * unstract-cloud (`specs/cloud/`), not here.
 *
 *   test("…", { tag: DIST.both }, async () => {});
 *   test.describe("…", { tag: DIST.cloud }, () => {});
 */

import { test as base } from "@playwright/test";
import { currentDistribution } from "../contract/distribution.ts";
import type { Distribution } from "../contract/registry.ts";

export { currentDistribution };

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
 * The config's `grepInvert`: drops tests tagged only for other
 * distributions before they are collected, so their beforeAll/afterAll hooks
 * do not run here either. A test with no distribution tag matches neither
 * lookahead, so it is still collected and the gate below fails it.
 */
export function otherDistributionsGrep(
  distribution: Distribution = currentDistribution(),
): RegExp {
  const current = TAG[distribution];
  const others = KNOWN.filter((t) => t !== current).map((t) => t.slice(1));
  return new RegExp(
    String.raw`^(?!.*${current}\b)(?=.*@(${others.join("|")})\b)`,
  );
}

/** Annotation type the gate leaves on every test it let through. */
export const GATE_ANNOTATION = "distribution";

/**
 * Applies `tagVerdict` to every collected test, as an auto fixture: the
 * config cannot express "fail when untagged", and a `grep` would drop such a
 * test without a trace. Tests for other distributions rarely reach it (see
 * `otherDistributionsGrep`); if one does, it skips.
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
      testInfo.annotations.push({
        type: GATE_ANNOTATION,
        description: currentDistribution(),
      });
      await use(undefined);
    },
    { auto: true },
  ],
});
