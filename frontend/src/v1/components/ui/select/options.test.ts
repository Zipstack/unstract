import { expect, it } from "vitest";
import { matchesQuery, type SelectOption, typeAheadIndex } from "./options";

const GPT: SelectOption = {
  value: "gpt-4o",
  label: "GPT-4o",
  keywords: ["openai", "omni"],
};

it("matches every option on an empty or blank query", () => {
  expect(matchesQuery(GPT, "")).toBe(true);
  expect(matchesQuery(GPT, "   ")).toBe(true);
});

it("matches a substring of the label, ignoring case and outer whitespace", () => {
  expect(matchesQuery(GPT, "pt-4")).toBe(true);
  expect(matchesQuery(GPT, "gpt-4O")).toBe(true);
  expect(matchesQuery(GPT, "  4o  ")).toBe(true);
  expect(matchesQuery(GPT, "claude")).toBe(false);
});

it("matches a substring of any keyword", () => {
  expect(matchesQuery(GPT, "OMN")).toBe(true);
  expect(matchesQuery(GPT, "open")).toBe(true);
  expect(matchesQuery({ value: "x", label: "X" }, "open")).toBe(false);
});

const MODELS: readonly SelectOption[] = [
  { value: "gemini", label: "Gemini" },
  { value: "gpt", label: "GPT-4o" },
  { value: "grok", label: "Grok", disabled: true },
  { value: "claude", label: "Claude" },
  { value: "gemma", label: "Gemma" },
  { value: "undefined", label: "Undefined" },
];

it("finds the first label after `from` starting with the buffer", () => {
  expect(typeAheadIndex(MODELS, "c", -1)).toBe(3);
  expect(typeAheadIndex(MODELS, "GP", 0)).toBe(1);
  expect(typeAheadIndex(MODELS, "gem", 1)).toBe(4);
});

it("wraps to the start of the list", () => {
  expect(typeAheadIndex(MODELS, "gemi", 3)).toBe(0);
  expect(typeAheadIndex(MODELS, "claude", 3)).toBe(3);
});

it("skips disabled options", () => {
  expect(typeAheadIndex(MODELS, "gr", -1)).toBe(-1);
  expect(typeAheadIndex(MODELS, "g", 1)).toBe(4);
});

it("cycles through matches on a repeated single character", () => {
  expect(typeAheadIndex(MODELS, "g", -1)).toBe(0);
  expect(typeAheadIndex(MODELS, "gg", 0)).toBe(1);
  expect(typeAheadIndex(MODELS, "ggg", 1)).toBe(4);
  expect(typeAheadIndex(MODELS, "gggg", 4)).toBe(0);
});

it("returns -1 when nothing matches", () => {
  expect(typeAheadIndex(MODELS, "z", 0)).toBe(-1);
  expect(typeAheadIndex([], "g", -1)).toBe(-1);
  expect(typeAheadIndex(MODELS, "", 0)).toBe(-1);
  expect(typeAheadIndex(MODELS, "", -1)).toBe(-1);
  expect(typeAheadIndex(MODELS, "u", -1)).toBe(5);
});
