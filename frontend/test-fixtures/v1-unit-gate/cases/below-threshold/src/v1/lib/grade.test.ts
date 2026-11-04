import { expect, it } from "vitest";
import { grade } from "./grade";

it("grades a top score", () => {
  expect(grade(95)).toBe("A");
});
