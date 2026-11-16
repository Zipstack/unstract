import {
  type CodeLine,
  type CodeToken,
  plural,
  type TokenKind,
} from "./tokens";

/*
 * The line model behind JsonView: a JSON document flattened once into the
 * lines of its two-space pretty print, each tagged with its depth and, for an
 * object or array, the index of its matching line. The tree and raw modes
 * render the same lines; collapsing a container skips the range up to its
 * closing line, so a toggle costs one pass over the visible lines and never
 * re-flattens.
 *
 * Two sources, one printer. A value prints exactly as
 * `JSON.stringify(value, null, 2)`. JSON text keeps its own spelling: numbers,
 * strings, key order and duplicate keys are printed as written, only
 * re-indented, so a 19-digit ID is never rounded (JSON.parse would).
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
  /** The key, `[index]`, or "root". */
  label: string;
  /** The line's tokens, indentation included. */
  tokens: CodeLine;
  /** For `open`: the index of the matching `close` line. */
  closeIndex?: number;
  /** For `close`: the index of the matching `open` line. */
  openIndex?: number;
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
 * Two-space pretty print of a value. `undefined` (and anything else
 * `JSON.stringify` cannot represent, such as a function) becomes "", and a
 * value it cannot serialise (a BigInt, a cycle) throws.
 */
export function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

// A document as the printer sees it: scalars carry their printed text.
type JsonNode =
  | Readonly<{ type: "scalar"; text: string; kind: TokenKind }>
  | Readonly<{ type: "array"; items: readonly JsonNode[] }>
  | Readonly<{
      type: "object";
      // Printed key (quoted, as written) and the decoded key for the pointer.
      entries: readonly (readonly [string, string, JsonNode])[];
    }>;

function fromValue(value: unknown): JsonNode {
  if (Array.isArray(value)) {
    return { type: "array", items: value.map(fromValue) };
  }
  if (value !== null && typeof value === "object") {
    return {
      type: "object",
      entries: Object.entries(value).map(
        ([k, v]) => [JSON.stringify(k), k, fromValue(v)] as const,
      ),
    };
  }
  if (typeof value === "string") {
    return { type: "scalar", text: JSON.stringify(value), kind: "string" };
  }
  if (typeof value === "number") {
    return { type: "scalar", text: JSON.stringify(value), kind: "number" };
  }
  return { type: "scalar", text: String(value), kind: "literal" };
}

/**
 * Reads already-validated JSON text into nodes, keeping each scalar's source
 * spelling. Callers validate with JSON.parse first, so this assumes
 * well-formed input.
 */
function fromText(text: string): JsonNode {
  let i = 0;
  const space = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) {
      i++;
    }
  };
  const string = (): string => {
    const start = i++;
    while (text[i] !== '"') {
      i += text[i] === "\\" ? 2 : 1;
    }
    i++;
    return text.slice(start, i);
  };
  const value = (): JsonNode => {
    space();
    const c = text[i];
    if (c === "{") {
      i++;
      const entries: [string, string, JsonNode][] = [];
      space();
      while (text[i] !== "}") {
        const key = string();
        space();
        i++; // :
        entries.push([key, JSON.parse(key) as string, value()]);
        space();
        if (text[i] === ",") {
          i++;
          space();
        }
      }
      i++;
      return { type: "object", entries };
    }
    if (c === "[") {
      i++;
      const items: JsonNode[] = [];
      space();
      while (text[i] !== "]") {
        items.push(value());
        space();
        if (text[i] === ",") {
          i++;
          space();
        }
      }
      i++;
      return { type: "array", items };
    }
    if (c === '"') {
      return { type: "scalar", text: string(), kind: "string" };
    }
    const start = i;
    while (i < text.length && !" \t\n\r,]}".includes(text[i])) {
      i++;
    }
    const word = text.slice(start, i);
    const kind: TokenKind =
      word === "true" || word === "false" || word === "null"
        ? "literal"
        : "number";
    return { type: "scalar", text: word, kind };
  };
  return value();
}

function escapePointer(segment: string): string {
  return segment.replaceAll("~", "~0").replaceAll("/", "~1");
}

function print(root: JsonNode): JsonLine[] {
  const lines: JsonLine[] = [];
  const walk = (
    node: JsonNode,
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
        : [...indent, { text: key, kind: "key" }, { text: ": " }];
    const comma: CodeToken[] = trailingComma ? [{ text: "," }] : [];
    if (node.type === "scalar") {
      lines.push({
        index: lines.length,
        kind: "leaf",
        depth,
        path,
        label,
        tokens: [...prefix, { text: node.text, kind: node.kind }, ...comma],
      });
      return;
    }
    const isArray = node.type === "array";
    const children: readonly (readonly [
      string | undefined,
      string,
      JsonNode,
    ])[] =
      node.type === "array"
        ? node.items.map((item, i) => [undefined, String(i), item] as const)
        : node.entries;
    const [open, close] = isArray ? ["[", "]"] : ["{", "}"];
    if (children.length === 0) {
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
    children.forEach(([childKey, name, child], i) => {
      walk(
        child,
        depth + 1,
        `${path}/${escapePointer(name)}`,
        isArray ? `[${name}]` : name,
        childKey,
        i < children.length - 1,
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
      openIndex,
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
        ? plural(children.length, "item")
        : plural(children.length, "key"),
    };
  };
  walk(root, 0, "", "root", undefined, false);
  return lines;
}

/**
 * Flattens a value into the lines of `JSON.stringify(value, null, 2)`
 * (`toJSON` applied, `undefined` and functions dropped from objects and nulled
 * in arrays). Returns no lines when the value has no JSON form (`undefined`);
 * throws when it cannot be serialised (a BigInt, a cycle).
 */
export function flattenJson(value: unknown): JsonLine[] {
  const json = JSON.stringify(value);
  return json === undefined ? [] : print(fromValue(JSON.parse(json)));
}

/**
 * Flattens JSON text into its re-indented lines, keeping every scalar, key
 * and key order exactly as written. Returns the parse error for invalid text.
 */
export function flattenJsonText(
  text: string,
):
  | Readonly<{ ok: true; lines: JsonLine[] }>
  | Readonly<{ ok: false; error: string }> {
  const parsed = parseJson(text);
  return parsed.ok ? { ok: true, lines: print(fromText(text)) } : parsed;
}

/**
 * Whether `error` is the engine running out of stack: a RangeError in V8 and
 * JavaScriptCore, an InternalError ("too much recursion") in Firefox.
 */
export function isTooDeep(error: unknown): boolean {
  return (
    error instanceof RangeError ||
    (error instanceof Error && error.name === "InternalError")
  );
}

/**
 * Re-indents JSON text the way JsonView shows it, keeping every number,
 * string and key as written (`formatJson(JSON.parse(text))` would round a
 * 19-digit ID). Returns `null` for invalid text or nesting too deep to print.
 */
export function formatJsonText(text: string): string | null {
  try {
    const result = flattenJsonText(text);
    return result.ok
      ? result.lines
          .map((line) => line.tokens.map((t) => t.text).join(""))
          .join("\n")
      : null;
  } catch (error) {
    // Too deep to print; any other error is a bug and is not hidden.
    if (isTooDeep(error)) {
      return null;
    }
    throw error;
  }
}

/**
 * The lines left showing when the containers whose opening-line indexes are
 * in `collapsed` are folded. Folds are keyed by index, not path: JSON text may
 * repeat a key, so two containers can share a path.
 */
export function visibleLines(
  lines: readonly JsonLine[],
  collapsed: ReadonlySet<number>,
): JsonLine[] {
  const out: JsonLine[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    out.push(line);
    // A folded container skips straight past its closing line.
    const folded = line.kind === "open" && collapsed.has(line.index);
    i = (folded ? (line.closeIndex ?? i) : i) + 1;
  }
  return out;
}

/** Opening-line indexes of every container at `depth` or deeper: the set to fold for "expand to depth". */
export function containersFrom(
  lines: readonly JsonLine[],
  depth: number,
): Set<number> {
  return new Set(
    lines
      .filter((line) => line.kind === "open" && line.depth >= depth)
      .map((line) => line.index),
  );
}
