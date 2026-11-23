import { expect, it } from "vitest";
import { removalDescription } from "./removal";

const BASE =
  "The document and every prompt output produced from it are removed.";
const covering = (ids: string[]) => ({ coverage: ids });
const ALL = ["a", "b", "c", "d"];

it("reads frame D08 when every prompt covers every document", () => {
  const prompts = [covering(ALL), covering(ALL), covering(ALL), covering(ALL)];
  expect(removalDescription("d", 4, prompts)).toBe(
    `${BASE} Coverage for all four prompts drops to 3 of 4.`,
  );
});

it("says only what is removed when coverage is not known", () => {
  expect(removalDescription("d", 4, undefined)).toBe(BASE);
  expect(removalDescription("d", 4, [])).toBe(BASE);
});

it("says nothing about coverage when no prompt covers the document", () => {
  expect(removalDescription("d", 4, [covering(["a", "b"])])).toBe(BASE);
});

it("names a single prompt", () => {
  expect(removalDescription("d", 4, [covering(ALL)])).toBe(
    `${BASE} Coverage for the prompt drops to 3 of 4.`,
  );
});

it("counts the prompts that lose the document when they end apart", () => {
  const prompts = [covering(ALL), covering(["a", "d"]), covering(["a"])];
  expect(removalDescription("d", 4, prompts)).toBe(
    `${BASE} Coverage drops by one document for two of three prompts.`,
  );
});

it("writes large counts as digits", () => {
  const prompts = Array.from({ length: 12 }, () => covering(ALL));
  expect(removalDescription("d", 4, prompts)).toBe(
    `${BASE} Coverage for all 12 prompts drops to 3 of 4.`,
  );
});

it("does not say all prompts when some never covered the document", () => {
  const prompts = [covering(ALL), covering(ALL), covering(["a", "b"])];
  expect(removalDescription("d", 4, prompts)).toBe(
    `${BASE} Coverage drops by one document for two of three prompts.`,
  );
});
