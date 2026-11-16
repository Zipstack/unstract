/**
 * Self-test: the distribution gate runs tests tagged for this distribution,
 * skips those tagged for another, and fails those with no distribution tag,
 * so an untagged or mistyped test cannot drop out of every run unnoticed.
 */

import {
  currentDistribution,
  DIST,
  expect,
  TAG,
  test,
} from "../../fixtures/index.ts";
import {
  GATE_ANNOTATION,
  otherDistributionsGrep,
  tagVerdict,
} from "../../fixtures/tags.ts";

test.describe("harness: distribution tags", { tag: DIST.all }, () => {
  test("a test tagged for this distribution runs", () => {
    expect(tagVerdict(DIST.both, "oss")).toEqual({ kind: "run" });
    expect(tagVerdict([TAG.cloud, "@slow"], "cloud")).toEqual({ kind: "run" });
  });

  test("a test tagged for another distribution is skipped", () => {
    expect(tagVerdict(DIST.cloud, "oss").kind).toBe("skip");
    expect(tagVerdict(DIST.both, "onprem").kind).toBe("skip");
  });

  test("an untagged or mistyped test fails", () => {
    expect(tagVerdict([], "oss").kind).toBe("fail");
    expect(tagVerdict(["@OSS"], "oss").kind).toBe("fail");
    expect(tagVerdict(["@os", "@slow"], "oss").kind).toBe("fail");
  });
});

/*
 * Deliberately untagged, and expected to fail: the gate fixture must reject it
 * before the body runs. If the gate stopped failing untagged tests, this would
 * pass, and an expected failure that passes is reported as a failure.
 */
test.fail("an untagged test is failed by the gate fixture", () => {});

test.describe("harness: distribution tags (gate)", { tag: DIST.all }, () => {
  test("the gate annotation names this run's distribution", () => {
    // Only the gate fixture leaves this annotation; the tags alone would be
    // there without it.
    expect(test.info().annotations).toContainEqual({
      type: GATE_ANNOTATION,
      description: currentDistribution(),
    });
  });

  test("the config drops only tests tagged solely for other distributions", () => {
    // Playwright matches grep against the title with its tags appended.
    const oss = otherDistributionsGrep("oss");
    expect(oss.test("cloud page @cloud")).toBe(true);
    expect(oss.test("on-prem page @onprem @cloud")).toBe(true);
    expect(oss.test("shared page @oss @cloud")).toBe(false);
    expect(oss.test("oss page @oss")).toBe(false);
    // Untagged and mistyped stay collected, so the gate can fail them.
    expect(oss.test("forgot the tag")).toBe(false);
    expect(oss.test("mistyped @OSS")).toBe(false);
    expect(oss.test("prefix only @ossx")).toBe(false);

    const cloud = otherDistributionsGrep("cloud");
    expect(cloud.test("oss page @oss")).toBe(true);
    expect(cloud.test("shared page @oss @cloud")).toBe(false);
    expect(cloud.test("forgot the tag")).toBe(false);

    const onprem = otherDistributionsGrep("onprem");
    expect(onprem.test("shared page @oss @cloud")).toBe(true);
    expect(onprem.test("everywhere @oss @cloud @onprem")).toBe(false);
  });
});
