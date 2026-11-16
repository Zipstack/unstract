import { cn } from "@v1/lib/cn";
import type { CodeLine, TokenKind } from "@v1/lib/code/tokens";
import type { JSX, ReactNode } from "react";

/** Each syntax kind's colour token; a run with no kind inherits the text colour. */
export const KIND_CLASS: Readonly<Record<TokenKind, string>> = {
  key: "ui:text-code-key",
  string: "ui:text-code-string",
  number: "ui:text-code-number",
  literal: "ui:text-code-literal",
  keyword: "ui:text-code-keyword",
  comment: "ui:text-code-comment ui:italic",
};

/**
 * A native button with v1's look: v1 ships no preflight, so the browser's
 * border, fill and font are reset here. Shared by every control in this module.
 */
export const BUTTON_BASE =
  "ui:border-0 ui:bg-transparent ui:font-sans ui:inline-flex ui:cursor-pointer ui:items-center ui:rounded-sm ui:text-muted-foreground ui:hover:bg-accent ui:hover:text-foreground ui:focus-visible:focus-ring";

/** A text button in a code toolbar ("Expand all", "Raw"). */
export const TOOLBAR_BUTTON = `${BUTTON_BASE} ui:h-7 ui:px-2 ui:text-body-small ui:font-medium`;

/** The mono text every code surface uses: the font-mono token and the mono type role. */
export const MONO = "ui:font-mono ui:text-mono";

/** Renders one line's tokens. */
export function Tokens({ line }: Readonly<{ line: CodeLine }>): JSX.Element {
  return (
    <>
      {line.map((token, i) =>
        token.kind ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: tokens have no identity beyond their position in the line.
          <span key={i} className={KIND_CLASS[token.kind]}>
            {token.text}
          </span>
        ) : (
          token.text
        ),
      )}
    </>
  );
}

/**
 * The width of the line-number gutter, in `ch`, for numbers up to `last`.
 * Set it as `style={{ "--code-gutter": gutterWidth(n) }}` on the container
 * so every row's gutter (`GUTTER`) lines up.
 */
export function gutterWidth(last: number): string {
  return `${String(Math.max(last, 1)).length}ch`;
}

export const GUTTER =
  "ui:w-(--code-gutter) ui:shrink-0 ui:box-content ui:pr-4 ui:text-right ui:text-muted-foreground ui:select-none";

export type LineRowProps = Readonly<{
  number?: number;
  showLineNumbers: boolean;
  wrap: boolean;
  children: ReactNode;
  className?: string;
}>;

/**
 * One rendered line: optional number gutter, then the content. A `span`, so
 * it may sit inside `<code>` (phrasing content only).
 */
export function LineRow({
  number,
  showLineNumbers,
  wrap,
  children,
  className,
}: LineRowProps): JSX.Element {
  return (
    <span
      data-slot="code-line"
      className={cn("ui:flex ui:min-h-lh", className)}
    >
      {showLineNumbers ? (
        <span aria-hidden className={GUTTER}>
          {number}
        </span>
      ) : null}
      <span
        className={cn(
          "ui:min-w-0 ui:flex-1",
          wrap ? "ui:whitespace-pre-wrap ui:break-all" : "ui:whitespace-pre",
        )}
      >
        {children}
      </span>
    </span>
  );
}
