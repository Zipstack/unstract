import { describe, expect, it } from "vitest";
import {
  type CustomDataRow,
  customDataFormSchema,
  customDataRows,
  isDefined,
  previewData,
  referencedVariables,
} from "./customData";

const parse = (rows: { key: string; value: string; json?: boolean }[]) =>
  customDataFormSchema.safeParse({
    rows: rows.map((r) => ({ json: false, ...r })),
  });

const issues = (rows: { key: string; value: string; json?: boolean }[]) => {
  const result = parse(rows);
  return result.success
    ? {}
    : Object.fromEntries(
        result.error.issues.map((i) => [i.path.join("."), i.message]),
      );
};

describe("customDataRows", () => {
  it("shows strings as typed and anything else as JSON", () => {
    expect(
      customDataRows({ code: "CYB", year: 2026, user: { name: "A" } }),
    ).toEqual([
      { key: "code", value: "CYB", json: false, loaded: "CYB" },
      { key: "year", value: "2026", json: true },
      { key: "user", value: '{"name":"A"}', json: true },
    ]);
  });

  it("has no rows for null or a value that is not an object", () => {
    expect(customDataRows(null)).toEqual([]);
    expect(customDataRows([1, 2])).toEqual([]);
  });
});

describe("customDataFormSchema", () => {
  it("round-trips nested values and keeps loaded numbers numbers", () => {
    const data = { code: "CYB", year: 2026, user: { name: "A" }, on: true };
    const result = customDataFormSchema.parse({ rows: customDataRows(data) });
    expect(result).toEqual({ custom_data: data });
  });

  it("keeps a loaded string as text while it is unchanged, even if it looks like JSON", () => {
    const data = { tbd: "[TBD] see contract", json: '{"a":1}', list: "[1,2]" };
    expect(
      customDataFormSchema.safeParse({ rows: customDataRows(data) }).data,
    ).toEqual({ custom_data: data });
  });

  it("reads an edited loaded string by the typed rule", () => {
    const [row] = customDataRows({ list: "[1]" });
    expect(
      parse([{ ...(row as CustomDataRow), value: "[1, 2]" }]).data,
    ).toEqual({ custom_data: { list: [1, 2] } });
  });

  it("stores a typed value as a string unless it starts an object or array", () => {
    expect(
      parse([
        { key: "a", value: "2026" },
        { key: "b", value: '{"x": [1]}' },
        { key: "c", value: "[1, 2]" },
      ]).data?.custom_data,
    ).toEqual({ a: "2026", b: { x: [1] }, c: [1, 2] });
  });

  it("lets a loaded number become text", () => {
    expect(parse([{ key: "y", value: "FY26", json: true }]).data).toEqual({
      custom_data: { y: "FY26" },
    });
  });

  it("rejects broken JSON, a missing key and a repeated key", () => {
    expect(
      issues([
        { key: "a", value: "{oops" },
        { key: "", value: "x" },
        { key: "a", value: "y" },
      ]),
    ).toEqual({
      "rows.0.value":
        "Enter valid JSON, or text that does not start with { or [",
      "rows.1.key": "Enter a key",
      "rows.2.key": "This key is already used",
    });
  });

  it("drops blank rows and saves no pairs as null", () => {
    expect(parse([{ key: " ", value: "" }]).data).toEqual({
      custom_data: null,
    });
    expect(parse([]).data).toEqual({ custom_data: null });
  });
});

describe("variables referenced in active prompts", () => {
  const prompts = [
    {
      prompt:
        "{{custom_data.a}} and {{custom_data.user.name}} {{custom_data.a}}",
    },
    { prompt: "{{custom_data.off}}", active: false },
    { prompt: "{{custom_data.note}}", prompt_type: "NOTES" },
    { prompt: null },
  ];

  it("lists each path once, skipping inactive prompts and notes", () => {
    expect(referencedVariables(prompts)).toEqual(["a", "user.name"]);
  });

  it("resolves nested paths against the data", () => {
    const data = { a: 1, user: { name: "x" }, empty: null };
    expect(isDefined(data, "a")).toBe(true);
    expect(isDefined(data, "user.name")).toBe(true);
    expect(isDefined(data, "user.email")).toBe(false);
    expect(isDefined(data, "empty.x")).toBe(false);
    expect(isDefined(null, "a")).toBe(false);
  });

  it("previews the rows as data, skipping values that do not parse", () => {
    expect(
      previewData([
        { key: "a", value: "{bad", json: false },
        { key: "b", value: '{"c": 1}', json: false },
        { key: "", value: "x", json: false },
      ]),
    ).toEqual({ b: { c: 1 } });
  });
});
