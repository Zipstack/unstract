import { expect, it } from "vitest";
import { CODE_LANGUAGES, highlightLines } from "./highlight";
import { lineText, splitLines } from "./tokens";

const kinds = (code: string, language: Parameters<typeof highlightLines>[1]) =>
  highlightLines(code, language)
    .flat()
    .filter((t) => t.kind)
    .map((t) => [t.text, t.kind]);

it("keeps the text of every line, for every language", () => {
  const code = 'a = "b"\n\n# c\r\nlast\n';
  for (const language of CODE_LANGUAGES) {
    expect(highlightLines(code, language).map(lineText)).toEqual(
      splitLines(code),
    );
  }
});

it("maps Prism token types onto the v1 kinds", () => {
  expect(kinds('{"a": 1, "b": [true, null, "x"]}', "json")).toEqual([
    ['"a"', "key"],
    ["1", "number"],
    ['"b"', "key"],
    ["true", "literal"],
    ["null", "literal"],
    ['"x"', "string"],
  ]);
  expect(kinds("def f():\n    return 'x'  # done", "python")).toEqual([
    ["def", "keyword"],
    ["f", "keyword"],
    ["return", "keyword"],
    ["'x'", "string"],
    ["# done", "comment"],
  ]);
  expect(kinds("# Title\n\nbody", "markdown")).toEqual([
    ["# Title", "keyword"],
  ]);
  expect(kinds("const n: number = 2;", "typescript")).toContainEqual([
    "const",
    "keyword",
  ]);
  expect(kinds("curl -X POST https://x", "bash")).toContainEqual([
    "curl",
    "keyword",
  ]);
  // Prism's YAML grammar leaves unquoted scalars plain.
  expect(kinds('key: "value"\nn: 3', "yaml")).toEqual([
    ["key", "key"],
    ['"value"', "string"],
    ["n", "key"],
    ["3", "number"],
  ]);
});

it("splits a token that spans lines and merges neighbours of one kind", () => {
  const lines = highlightLines('"""a\nb"""', "python");
  expect(lines).toEqual([
    [{ text: '"""a', kind: "string" }],
    [{ text: 'b"""', kind: "string" }],
  ]);
});

it("leaves plain text alone and returns no lines for nothing", () => {
  expect(highlightLines("x = 1\n\ny", "text")).toEqual([
    [{ text: "x = 1" }],
    [],
    [{ text: "y" }],
  ]);
  expect(highlightLines("", "json")).toEqual([]);
  expect(highlightLines("\n", "json")).toEqual([[]]);
});

it("splits lines on any line ending, without an empty last line", () => {
  expect(splitLines("")).toEqual([]);
  expect(splitLines("a\r\nb\rc\n")).toEqual(["a", "b", "c"]);
  expect(splitLines("a\n\n")).toEqual(["a", ""]);
});
