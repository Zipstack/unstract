import { cn } from "@v1/lib/cn";
import { type CodeLanguage, highlightLines } from "@v1/lib/code/highlight";
import { type ComponentProps, type JSX, type ReactNode, useMemo } from "react";
import { gutterWidth, LineRow, MONO, Tokens } from "./CodeLines";
import { CopyButton } from "./CopyButton";

/** Display names, used for the default accessible label ("Python code"). */
export const LANGUAGE_NAME: Readonly<Record<CodeLanguage, string>> = {
  json: "JSON",
  bash: "Shell",
  python: "Python",
  javascript: "JavaScript",
  typescript: "TypeScript",
  yaml: "YAML",
  markdown: "Markdown",
  text: "Plain text",
};

export type CodeBlockProps = Omit<ComponentProps<"div">, "children" | "title"> &
  Readonly<{
    code: string;
    /** Highlighting grammar; `text` (the default) is not highlighted. */
    language?: CodeLanguage;
    /** Shown in the header, left. */
    title?: ReactNode;
    /** Extra controls in the header, before the copy button. */
    actions?: ReactNode;
    /** Shows a copy button in the header (default on). */
    copyable?: boolean;
    showLineNumbers?: boolean;
    /** Wraps long lines instead of scrolling sideways. */
    wrap?: boolean;
    /** Names the scrollable code region; defaults to the title or the language. */
    "aria-label"?: string;
  }>;

/**
 * Read-only, highlighted code. The block grows with its content; constrain it
 * with a class (`className="ui:max-h-80"`) and the code area scrolls.
 */
export function CodeBlock({
  code,
  language = "text",
  title,
  actions,
  copyable = true,
  showLineNumbers = false,
  wrap = false,
  "aria-label": ariaLabel,
  className,
  ...props
}: CodeBlockProps): JSX.Element {
  const lines = useMemo(() => highlightLines(code, language), [code, language]);
  const label =
    ariaLabel ??
    (typeof title === "string" ? title : `${LANGUAGE_NAME[language]} code`);
  const header = title != null || actions != null || copyable;
  return (
    <div
      data-slot="code-block"
      data-language={language}
      className={cn(
        "ui:flex ui:min-h-0 ui:flex-col ui:overflow-hidden ui:rounded-lg ui:border ui:border-border ui:bg-muted ui:text-foreground",
        className,
      )}
      {...props}
    >
      {header ? (
        <div
          data-slot="code-block-header"
          className="ui:flex ui:items-center ui:gap-2 ui:border-b ui:border-border ui:py-1 ui:pr-1 ui:pl-3"
        >
          <div className="ui:min-w-0 ui:flex-1 ui:truncate ui:text-caption ui:font-medium ui:text-muted-foreground">
            {title}
          </div>
          {actions}
          {copyable ? <CopyButton text={code} label="Copy code" /> : null}
        </div>
      ) : null}
      <section
        aria-label={label}
        // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable (WCAG 2.1.1)
        tabIndex={0} // NOSONAR: a scrollable region must be focusable (WCAG 2.1.1)
        className="ui:min-h-0 ui:flex-1 ui:overflow-auto ui:focus-visible:focus-ring"
      >
        <pre
          className={cn("ui:m-0 ui:p-3", MONO)}
          style={{ "--code-gutter": gutterWidth(lines.length) }}
        >
          <code>
            {lines.map((line, i) => (
              <LineRow
                // biome-ignore lint/suspicious/noArrayIndexKey: a line is identified by its position.
                key={i}
                number={i + 1}
                showLineNumbers={showLineNumbers}
                wrap={wrap}
              >
                <Tokens line={line} />
              </LineRow>
            ))}
          </code>
        </pre>
      </section>
    </div>
  );
}
