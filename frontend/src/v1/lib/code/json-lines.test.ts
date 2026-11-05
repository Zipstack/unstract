import { largeJson, STATEMENT } from "@v1/test/fixtures/json";
import { expect, it } from "vitest";
import {
  containersFrom,
  flattenJson,
  formatJson,
  parseJson,
  visibleLines,
} from "./json-lines";
import { lineText } from "./tokens";

const text = (value: unknown) =>
  flattenJson(value)
    .map((line) => lineText(line.tokens))
    .join("\n");

it("prints exactly what JSON.stringify(value, null, 2) prints", () => {
  for (const value of [
    STATEMENT,
    [],
    {},
    { a: [] },
    [1, "two", null, false, { "a/b": { "~": 1 } }],
    "solo",
    0,
    largeJson(300),
  ]) {
    expect(text(value)).toBe(JSON.stringify(value, null, 2));
  }
});

it("follows JSON.stringify for values JSON cannot hold", () => {
  const value = {
    when: new Date(Date.UTC(2026, 0, 2)),
    skip: undefined,
    fn: () => 1,
    list: [undefined, Number.NaN, Number.POSITIVE_INFINITY],
  };
  expect(text(value)).toBe(JSON.stringify(value, null, 2));
  expect(flattenJson(undefined)).toEqual([]);
  expect(() => flattenJson({ n: BigInt(1) })).toThrow();
});

it("tags keys, strings, numbers and literals", () => {
  const [, line] = flattenJson({ a: "x" });
  expect(line.tokens).toEqual([
    { text: "  " },
    { text: '"a"', kind: "key" },
    { text: ": " },
    { text: '"x"', kind: "string" },
  ]);
  const kinds = flattenJson([1, true, null]).flatMap((l) =>
    l.tokens.filter((t) => t.kind).map((t) => t.kind),
  );
  expect(kinds).toEqual(["number", "literal", "literal"]);
});

it("pairs each container's opening and closing lines, with a summary and pointer paths", () => {
  const lines = flattenJson(STATEMENT);
  const rewards = lines.find((l) => l.label === "rewards");
  expect(rewards).toMatchObject({
    kind: "open",
    depth: 1,
    path: "/rewards",
    summary: "3 keys",
  });
  const close = lines[rewards?.closeIndex as number];
  expect(close).toMatchObject({ kind: "close", path: "/rewards", depth: 1 });
  expect(lineText(close.tokens)).toBe("  },");
  expect(rewards?.closeTokens).toEqual([{ text: "}" }, { text: "," }]);
  const transactions = lines.find((l) => l.label === "transactions");
  expect(transactions?.summary).toBe("2 items");
  expect(lines.find((l) => l.path === "/transactions/0")?.label).toBe("[0]");
  expect(flattenJson([[1]])[1].summary).toBe("1 item");
  expect(flattenJson({ a: { b: 1 } })[1].summary).toBe("1 key");
  expect(flattenJson({ "a/b": { "~": 1 } })[1].path).toBe("/a~1b");
  expect(flattenJson({ "a/b": { "~": 1 } })[2].path).toBe("/a~1b/~0");
});

it("hides a folded container's contents but keeps its opening line", () => {
  const lines = flattenJson(STATEMENT);
  const shown = visibleLines(lines, new Set(["/rewards", "/transactions"]));
  expect(shown.map((l) => lineText(l.tokens))).toEqual([
    "{",
    '  "fees": 0,',
    '  "rewards": {',
    '  "website": "americanexpress.com",',
    '  "autopay": true,',
    '  "previous_balance": null,',
    '  "transactions": [',
    "}",
  ]);
  expect(visibleLines(lines, new Set([""]))).toHaveLength(1);
  expect(visibleLines(lines, new Set())).toHaveLength(lines.length);
});

it("lists the containers at or below a depth", () => {
  const lines = flattenJson(STATEMENT);
  expect([...containersFrom(lines, 1)]).toEqual([
    "/rewards",
    "/transactions",
    "/transactions/0",
    "/transactions/1",
  ]);
  expect([...containersFrom(lines, 2)]).toEqual([
    "/transactions/0",
    "/transactions/1",
  ]);
  expect(containersFrom(lines, Number.POSITIVE_INFINITY).size).toBe(0);
});

it("the large fixture is exactly 5,000 lines", () => {
  expect(flattenJson(largeJson())).toHaveLength(5000);
  expect(flattenJson(largeJson(1234))).toHaveLength(1234);
});

it("parses without throwing and formats like JSON.stringify", () => {
  expect(parseJson('{"a":1}')).toEqual({ ok: true, value: { a: 1 } });
  const bad = parseJson("{a:1}");
  expect(bad.ok).toBe(false);
  expect(bad.ok ? "" : bad.error).toMatch(/JSON/);
  expect(formatJson({ a: [1] })).toBe('{\n  "a": [\n    1\n  ]\n}');
  expect(formatJson(undefined)).toBe("");
});
