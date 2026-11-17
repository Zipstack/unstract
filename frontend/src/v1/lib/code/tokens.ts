/**
 * The token model every v1 code view renders: lines of text runs, each run
 * optionally tagged with a syntax kind. Kinds map one to one onto the
 * `code-*` colour tokens (`ui:text-code-key` and so on); a run with no kind
 * takes the surrounding text colour.
 */
export const TOKEN_KINDS = [
  "key",
  "string",
  "number",
  "literal",
  "keyword",
  "comment",
] as const;
export type TokenKind = (typeof TOKEN_KINDS)[number];

export type CodeToken = Readonly<{ text: string; kind?: TokenKind }>;
export type CodeLine = readonly CodeToken[];

/** "1 key", "3 keys": `count` and the word, plural unless it is one. */
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** The text of a line, tokens joined. */
export function lineText(line: CodeLine): string {
  return line.map((token) => token.text).join("");
}

/**
 * Normalises line endings to `\n` and splits into lines. A trailing newline
 * does not add an empty last line, and an empty string has no lines.
 */
export function splitLines(text: string): string[] {
  if (text === "") {
    return [];
  }
  const normalised = text.replace(/\r\n?/g, "\n");
  const body = normalised.endsWith("\n") ? normalised.slice(0, -1) : normalised;
  return body.split("\n");
}
