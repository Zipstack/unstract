import { expect, it } from "vitest";
import { cn } from "./cn";

it("merges conflicting prefixed utilities, keeping the last", () => {
  expect(cn("v1:p-2 v1:p-4")).toBe("v1:p-4");
  expect(cn("v1:bg-background", false, "v1:bg-card")).toBe("v1:bg-card");
});

it("keeps unrelated and variant classes", () => {
  expect(cn("v1:flex v1:dark:bg-card", ["v1:gap-2"])).toBe(
    "v1:flex v1:dark:bg-card v1:gap-2",
  );
});
