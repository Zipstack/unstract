import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const source = fs.readFileSync(
  path.resolve(__dirname, "ToolsMain.jsx"),
  "utf-8",
);

describe("ToolsMain source-text checks", () => {
  it("reads isSinglePassExtractLoading via getState()", () => {
    expect(source).toContain("useCustomToolStore.getState()");
  });

  it("guards promptOutputApi behind isSinglePassExtractLoading check", () => {
    expect(source).toContain(
      "if (isSinglePassExtractLoading) {\n      return;\n    }",
    );
  });
});
