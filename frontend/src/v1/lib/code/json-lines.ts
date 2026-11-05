import type { CodeLine, CodeToken } from "./tokens";

/*
 * The line model behind JsonView: a JSON value flattened once into the lines
 * of its two-space pretty print (exactly `JSON.stringify(value, null, 2)`),
 * each tagged with its depth and, for an object or array, the index of its
 * closing line. The tree and raw modes render the same lines; collapsing a
 * container skips the range up to its closing line, so a toggle costs one
 * pass over the visible lines and never re-flattens.
 */

export type JsonLineKind = "open" | "close" | "leaf";

export type JsonLine = Readonly<{
  /** Position in the fully expanded document, from 0. */
  index: number;
  kind: JsonLineKind;
  depth: number;
  /**
   * A JSON Pointer to the value the line belongs to ("" for the root), so
   * the opening and closing lines of one container share it.
   */
  path: string;
  /** What a screen reader calls the line: the key, `[index]`, or "root". */
  label: string;
  /** The line's tokens, indentation included. */
  tokens: CodeLine;
  /** For `open`: the index of the matching `close` line. */
  closeIndex?: number;
  /** For `open`: the closing bracket and any trailing comma, shown when collapsed. */
  closeTokens?: CodeLine;
  /** For `open`: "3 keys" or "2 items", shown when collapsed. */
  summary?: string;
}>;

export type JsonParseResult =
  | Readonly<{ ok: true; value: unknown }>
  | Readonly<{ ok: false; error: string }>;

/** Parses JSON text; never throws. */
export function parseJson(text: string): JsonParseResult {
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Two-space pretty print, as JsonView shows it and copies it. `undefined`
 * (and anything else `JSON.stringify` cannot represent, such as a function)
 * becomes "", and a value it cannot serialise (a BigInt, a cycle) throws.
 */
export function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

function escapePointer(segment: string): string {
  return segment.replaceAll("~", "~0").replaceAll("/", "~1");
}

function scalarToken(value: unknown): CodeToken {
  if (typeof value === "string") {
    return { text: JSON.stringify(value), kind: "string" };
  }
  if (typeof value === "number") {
    return { text: JSON.stringify(value), kind: "number" };
  }
  // null and booleans; normalise() has already removed everything else.
  return { text: String(value), kind: "literal" };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/**
 * The value as JSON.stringify sees it: toJSON applied, undefined, functions
 * and symbols dropped from objects and nulled in arrays, non-finite numbers
 * nulled. Round-tripping through JSON is exact for these rules and fast for
 * the payload sizes JsonView is built for.
 */
function normalise(value: unknown): unknown {
  const text = JSON.stringify(value);
  return text === undefined ? undefined : JSON.parse(text);
}

/**
 * Flattens a value into its pretty-printed lines. Returns no lines when the
 * value has no JSON form (`undefined`); throws when it cannot be serialised.
 */
export function flattenJson(value: unknown): JsonLine[] {
  const root = normalise(value);
  if (root === undefined) {
    return [];
  }
  const lines: JsonLine[] = [];

  const walk = (
    node: unknown,
    depth: number,
    path: string,
    label: string,
    key: string | undefined,
    trailingComma: boolean,
  ): void => {
    const indent: CodeToken[] = depth > 0 ? [{ text: "  ".repeat(depth) }] : [];
    const prefix: CodeToken[] =
      key === undefined
        ? indent
        : [
            ...indent,
            { text: JSON.stringify(key), kind: "key" },
            { text: ": " },
          ];
    const comma: CodeToken[] = trailingComma ? [{ text: "," }] : [];

    const isArray = Array.isArray(node);
    if (node === null || typeof node !== "object") {
      lines.push({
        index: lines.length,
        kind: "leaf",
        depth,
        path,
        label,
        tokens: [...prefix, scalarToken(node), ...comma],
      });
      return;
    }
    const entries: [string, unknown][] = isArray
      ? (node as unknown[]).map((v, i) => [String(i), v])
      : Object.entries(node as Record<string, unknown>);
    const [open, close] = isArray ? ["[", "]"] : ["{", "}"];
    if (entries.length === 0) {
      lines.push({
        index: lines.length,
        kind: "leaf",
        depth,
        path,
        label,
        tokens: [...prefix, { text: `${open}${close}` }, ...comma],
      });
      return;
    }
    const openIndex = lines.length;
    // Placeholder; replaced once the close index is known.
    lines.push(undefined as unknown as JsonLine);
    entries.forEach(([childKey, child], i) => {
      walk(
        child,
        depth + 1,
        `${path}/${escapePointer(childKey)}`,
        isArray ? `[${childKey}]` : childKey,
        isArray ? undefined : childKey,
        i < entries.length - 1,
      );
    });
    const closeTokens: CodeToken[] = [{ text: close }, ...comma];
    const closeIndex = lines.length;
    lines.push({
      index: closeIndex,
      kind: "close",
      depth,
      path,
      label,
      tokens: [...indent, ...closeTokens],
    });
    lines[openIndex] = {
      index: openIndex,
      kind: "open",
      depth,
      path,
      label,
      tokens: [...prefix, { text: open }],
      closeIndex,
      closeTokens,
      summary: isArray
        ? plural(entries.length, "item", "items")
        : plural(entries.length, "key", "keys"),
    };
  };

  walk(root, 0, "", "root", undefined, false);
  return lines;
}

/** The lines left showing when the containers whose paths are in `collapsed` are folded. */
export function visibleLines(
  lines: readonly JsonLine[],
  collapsed: ReadonlySet<string>,
): JsonLine[] {
  const out: JsonLine[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    out.push(line);
    if (line.kind === "open" && collapsed.has(line.path)) {
      i = line.closeIndex ?? i;
    }
  }
  return out;
}

/** Paths of every container at `depth` or deeper: the set to fold for "expand to depth". */
export function containersFrom(
  lines: readonly JsonLine[],
  depth: number,
): Set<string> {
  return new Set(
    lines
      .filter((line) => line.kind === "open" && line.depth >= depth)
      .map((line) => line.path),
  );
}
