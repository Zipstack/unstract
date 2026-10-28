import { expect, it } from "vitest";
import { cn } from "./cn";

it("merges conflicting prefixed utilities, keeping the last", () => {
  expect(cn("ui:p-2 ui:p-4")).toBe("ui:p-4");
  expect(cn("ui:bg-background", false, "ui:bg-card")).toBe("ui:bg-card");
});

it("keeps unrelated and variant classes", () => {
  expect(cn("ui:flex ui:dark:bg-card", ["ui:gap-2"])).toBe(
    "ui:flex ui:dark:bg-card ui:gap-2",
  );
});

it("leaves unprefixed classes alone, so the merge is scoped to the ui prefix", () => {
  expect(cn("p-2 p-4")).toBe("p-2 p-4");
});
