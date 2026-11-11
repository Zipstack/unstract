/**
 * Self-test: the distribution gate runs tests tagged for this distribution,
 * skips those tagged for another, and fails those with no distribution tag,
 * so an untagged or mistyped test cannot drop out of every run unnoticed.
 */

import { DIST, expect, TAG, test } from "../../fixtures/index.ts";
import { tagVerdict } from "../../fixtures/tags.ts";

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

  test("this test went through the gate", () => {
    expect(test.info().tags).toEqual(expect.arrayContaining(DIST.all));
  });
});
