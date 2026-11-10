import { expect, it } from "vitest";
import { matchesQuery, type SelectOption } from "./options";

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
