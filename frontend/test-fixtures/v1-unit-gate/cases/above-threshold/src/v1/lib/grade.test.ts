import { expect, it } from "vitest";
import { grade } from "./grade";

it.each([
  [95, "A"],
  [85, "B"],
  [75, "C"],
  [65, "D"],
])("grades %i as %s", (score, letter) => {
  expect(grade(score)).toBe(letter);
});
