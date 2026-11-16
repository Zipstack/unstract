import bash from "refractor/bash";
import clike from "refractor/clike";
import { refractor } from "refractor/core";
import javascript from "refractor/javascript";
import json from "refractor/json";
import markdown from "refractor/markdown";
import markup from "refractor/markup";
import python from "refractor/python";
import typescript from "refractor/typescript";
import yaml from "refractor/yaml";
import {
  type CodeLine,
  type CodeToken,
  splitLines,
  type TokenKind,
} from "./tokens";

/*
 * Syntax highlighting with refractor 5 (Prism's grammars as ES modules, no
 * global `Prism`). Only these grammars are registered, so the bundle carries
 * nothing else; dependencies first (markdown needs markup, javascript needs
 * clike). refractor's own instance is shared with nothing else in v1; v0 uses
 * `prismjs`, a separate copy with its own global, so registering here never
 * changes v0's highlighting.
 *
 * The output is our token model, never Prism's `token` / `language-*` class
 * names: v0's global Prism theme styles those, and it would reach v1.
 */
for (const grammar of [
  markup,
  clike,
  javascript,
  typescript,
  json,
  bash,
  python,
  yaml,
  markdown,
]) {
  refractor.register(grammar);
}

export const CODE_LANGUAGES = [
  "json",
  "bash",
  "python",
  "javascript",
  "typescript",
  "yaml",
  "markdown",
  "text",
] as const;
export type CodeLanguage = (typeof CODE_LANGUAGES)[number];

// Prism token types → our kinds. A type not listed keeps the parent's kind.
const KIND_BY_TYPE: Readonly<Record<string, TokenKind>> = {
  property: "key",
  key: "key",
  "attr-name": "key",
  tag: "key",
  string: "string",
  "attr-value": "string",
  char: "string",
  url: "string",
  regex: "string",
  "template-string": "string",
  "triple-quoted-string": "string",
  number: "number",
  boolean: "literal",
  null: "literal",
  constant: "literal",
  keyword: "keyword",
  title: "keyword",
  builtin: "keyword",
  important: "keyword",
  function: "keyword",
  "class-name": "keyword",
  comment: "comment",
  prolog: "comment",
  doctype: "comment",
  shebang: "comment",
};

// The parts of a hast tree refractor emits, typed structurally so v1 does not
// depend on which `@types/hast` major the lockfile hoists.
type HastNode =
  | Readonly<{ type: "text"; value: string }>
  | Readonly<{
      type: "element";
      properties?: Readonly<{ className?: unknown }>;
      children: readonly HastNode[];
    }>
  | Readonly<{ type: string; children?: readonly HastNode[] }>;

function kindOf(node: HastNode, inherited?: TokenKind): TokenKind | undefined {
  if (node.type !== "element" || !("properties" in node)) {
    return inherited;
  }
  const classes = node.properties?.className;
  if (!Array.isArray(classes)) {
    return inherited;
  }
  for (const name of classes) {
    const kind = typeof name === "string" ? KIND_BY_TYPE[name] : undefined;
    if (kind) {
      return kind;
    }
  }
  return inherited;
}

function collect(
  node: HastNode,
  kind: TokenKind | undefined,
  out: CodeToken[],
): void {
  if (node.type === "text" && "value" in node) {
    out.push(kind ? { text: node.value, kind } : { text: node.value });
    return;
  }
  const own = kindOf(node, kind);
  for (const child of ("children" in node ? node.children : undefined) ?? []) {
    collect(child, own, out);
  }
}

/** Splits a flat run list at newlines into lines, merging adjacent same-kind runs. */
function toLines(tokens: readonly CodeToken[]): CodeLine[] {
  const lines: CodeToken[][] = [[]];
  for (const token of tokens) {
    const parts = token.text.split("\n");
    parts.forEach((part, i) => {
      if (i > 0) {
        lines.push([]);
      }
      if (part === "") {
        return;
      }
      const line = lines[lines.length - 1];
      const last = line[line.length - 1];
      if (last && last.kind === token.kind) {
        line[line.length - 1] = { ...last, text: last.text + part };
      } else {
        line.push(
          token.kind ? { text: part, kind: token.kind } : { text: part },
        );
      }
    });
  }
  return lines;
}

/**
 * Highlights `code` as `language` and returns one token list per line, with
 * the same line split as `splitLines` (CRLF normalised, no empty last line
 * for a trailing newline). `text` is never highlighted.
 */
export function highlightLines(
  code: string,
  language: CodeLanguage,
): CodeLine[] {
  const source = splitLines(code).join("\n");
  if (source === "" && code === "") {
    return [];
  }
  if (language === "text") {
    return source
      .split("\n")
      .map((line) => (line === "" ? [] : [{ text: line }]));
  }
  const tokens: CodeToken[] = [];
  collect(refractor.highlight(source, language) as HastNode, undefined, tokens);
  return toLines(tokens);
}
