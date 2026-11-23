import { describe, expect, it } from "vitest";
import {
  GRAMMAR_LIMIT,
  grammarFormSchema,
  grammarRows,
  splitSynonyms,
} from "./grammar";

const issues = (rows: { word: string; synonyms: string }[]) => {
  const result = grammarFormSchema.safeParse({ rows });
  return result.success
    ? {}
    : Object.fromEntries(
        result.error.issues.map((i) => [i.path.join("."), i.message]),
      );
};

describe("grammar", () => {
  it("shows equivalents comma-separated and saves them as a list", () => {
    const rows = grammarRows({ Amt: ["Amount", "Amt."] });
    expect(rows).toEqual([{ word: "Amt", synonyms: "Amount, Amt." }]);
    expect(grammarFormSchema.parse({ rows })).toEqual({
      prompt_grammer: { Amt: ["Amount", "Amt."] },
    });
  });

  it("has no rows for null", () => {
    expect(grammarRows(null)).toEqual([]);
  });

  it("trims equivalents, drops empties and repeats", () => {
    expect(splitSynonyms(" a, ,b,a ")).toEqual(["a", "b"]);
  });

  it("drops blank rows, which Add synonym leaves until filled", () => {
    expect(
      grammarFormSchema.parse({ rows: [{ word: " ", synonyms: " , " }] }),
    ).toEqual({ prompt_grammer: {} });
  });

  it("asks for the missing half of a row and refuses a repeated word", () => {
    expect(
      issues([
        { word: "BoA", synonyms: "" },
        { word: "", synonyms: "Statement" },
        { word: "BoA", synonyms: "Bank" },
      ]),
    ).toEqual({
      "rows.0.synonyms": "Add at least one equivalent",
      "rows.1.word": "Enter a word",
      "rows.2.word": "This word is already listed",
    });
  });

  it(`caps the list at ${GRAMMAR_LIMIT} words`, () => {
    const rows = Array.from({ length: GRAMMAR_LIMIT + 1 }, (_, i) => ({
      word: `w${i}`,
      synonyms: "x",
    }));
    expect(issues(rows)).toEqual({
      rows: `Up to ${GRAMMAR_LIMIT} words. Remove 1 to save.`,
    });
    expect(issues(rows.slice(1))).toEqual({});
  });
});
