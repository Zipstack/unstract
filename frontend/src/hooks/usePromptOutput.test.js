import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const source = fs.readFileSync(
  path.resolve(__dirname, "usePromptOutput.js"),
  "utf-8",
);

describe("usePromptOutput source-text checks", () => {
  it("updateCoverage uses getState() instead of stale closure", () => {
    expect(source).toContain("useCustomToolStore.getState()");
  });

  it("updateCoverage does NOT compare via stale selectedDoc closure", () => {
    expect(source).not.toContain("=== selectedDoc?.document_id");
  });
});
