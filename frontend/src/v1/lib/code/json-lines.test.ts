import { largeJson, STATEMENT } from "@v1/test/fixtures/json";
import { expect, it } from "vitest";
import {
  containersFrom,
  flattenJson,
  flattenJsonText,
  formatJson,
  formatJsonText,
  isTooDeep,
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
  expect(close).toMatchObject({
    kind: "close",
    path: "/rewards",
    depth: 1,
    openIndex: rewards?.index,
  });
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
  const at = (path: string) =>
    lines.find((l) => l.kind === "open" && l.path === path)?.index as number;
  const shown = visibleLines(
    lines,
    new Set([at("/rewards"), at("/transactions")]),
  );
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
  expect(visibleLines(lines, new Set([0]))).toHaveLength(1);
  expect(visibleLines(lines, new Set())).toHaveLength(lines.length);
});

it("lists the containers at or below a depth", () => {
  const lines = flattenJson(STATEMENT);
  const paths = (set: Set<number>) => [...set].map((i) => lines[i].path);
  expect(paths(containersFrom(lines, 1))).toEqual([
    "/rewards",
    "/transactions",
    "/transactions/0",
    "/transactions/1",
  ]);
  expect(paths(containersFrom(lines, 2))).toEqual([
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

const textOf = (text: string) => {
  const result = flattenJsonText(text);
  return result.ok
    ? result.lines.map((line) => lineText(line.tokens)).join("\n")
    : result.error;
};

it("prints JSON text as JSON.stringify would, re-indented, for ordinary documents", () => {
  for (const value of [
    STATEMENT,
    [],
    {},
    { a: [] },
    "solo",
    0,
    largeJson(300),
  ]) {
    expect(textOf(JSON.stringify(value))).toBe(JSON.stringify(value, null, 2));
  }
  expect(textOf(' {\n\t"a" :\r\n [ 1 ,true ] }\n')).toBe(
    '{\n  "a": [\n    1,\n    true\n  ]\n}',
  );
});

it("keeps JSON text as written: big integers, number spelling, escapes, key order and duplicates", () => {
  const source =
    '{"acct":4111111111111111111,"amt":1.10,"e":1E2,"2":"b","1":"a","s":"q\\"\\u00e9\\\\","a":1,"a":2}';
  expect(textOf(source)).toBe(
    [
      "{",
      '  "acct": 4111111111111111111,',
      '  "amt": 1.10,',
      '  "e": 1E2,',
      '  "2": "b",',
      '  "1": "a",',
      '  "s": "q\\"\\u00e9\\\\",',
      '  "a": 1,',
      '  "a": 2',
      "}",
    ].join("\n"),
  );
  const result = flattenJsonText(source);
  const lines = result.ok ? result.lines : [];
  expect(lines[1].tokens).toEqual([
    { text: "  " },
    { text: '"acct"', kind: "key" },
    { text: ": " },
    { text: "4111111111111111111", kind: "number" },
    { text: "," },
  ]);
  expect(lines.find((l) => l.label === "s")?.path).toBe("/s");
  // A repeated key gives two lines with one path; folds key on index, not path.
  expect(lines.filter((l) => l.path === "/a")).toHaveLength(2);
});

it("keys nested text containers like values, and reports invalid text", () => {
  const result = flattenJsonText('{"a/b":{"~":[null,false]}}');
  const lines = result.ok ? result.lines : [];
  expect(lines.map((l) => l.path)).toEqual([
    "",
    "/a~1b",
    "/a~1b/~0",
    "/a~1b/~0/0",
    "/a~1b/~0/1",
    "/a~1b/~0",
    "/a~1b",
    "",
  ]);
  expect(lines[3].tokens.at(-2)).toEqual({ text: "null", kind: "literal" });
  const bad = flattenJsonText("{a:1}");
  expect(bad.ok).toBe(false);
});

it("formatJsonText re-indents without changing a character of any value", () => {
  expect(formatJsonText('{"id":4111111111111111111,"n":[1.10]}')).toBe(
    '{\n  "id": 4111111111111111111,\n  "n": [\n    1.10\n  ]\n}',
  );
  expect(formatJsonText("{bad")).toBeNull();
  expect(formatJsonText(`${"[".repeat(20000)}${"]".repeat(20000)}`)).toBeNull();
});

it("isTooDeep knows each engine's stack-overflow error, and nothing else", () => {
  expect(isTooDeep(new RangeError("Maximum call stack size exceeded"))).toBe(
    true,
  );
  const firefox = new Error("too much recursion");
  firefox.name = "InternalError";
  expect(isTooDeep(firefox)).toBe(true);
  expect(isTooDeep(new TypeError("x is undefined"))).toBe(false);
  expect(isTooDeep("RangeError")).toBe(false);
});
