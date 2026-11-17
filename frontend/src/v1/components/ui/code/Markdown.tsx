import { cn } from "@v1/lib/cn";
import { CODE_LANGUAGES, type CodeLanguage } from "@v1/lib/code/highlight";
import {
  type ComponentProps,
  createContext,
  type JSX,
  useContext,
} from "react";
import ReactMarkdown, { uriTransformer } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock, LANGUAGE_NAME } from "./CodeBlock";
import { InlineCode } from "./InlineCode";

/** Fence names that mean one of our grammars ("```py"). */
const LANGUAGE_ALIAS: Readonly<Record<string, CodeLanguage>> = {
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  py: "python",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  curl: "bash",
  yml: "yaml",
  md: "markdown",
  txt: "text",
  plaintext: "text",
};

function fenceLanguage(className: string | undefined): CodeLanguage {
  const name = /language-([\w-]+)/.exec(className ?? "")?.[1]?.toLowerCase();
  if (!name) {
    return "text";
  }
  if ((CODE_LANGUAGES as readonly string[]).includes(name)) {
    return name as CodeLanguage;
  }
  // Own keys only: a fence named `constructor` must not find Object's.
  return Object.hasOwn(LANGUAGE_ALIAS, name) ? LANGUAGE_ALIAS[name] : "text";
}

/** An absolute http(s) link opens in a new tab; anything else stays in place. */
function isExternal(href: string | undefined): boolean {
  return /^https?:\/\//i.test(href ?? "");
}

type Props<T extends keyof JSX.IntrinsicElements> = ComponentProps<T> & {
  node?: unknown;
  level?: number;
  depth?: number;
};
type CodeProps = Props<"code"> & { inline?: boolean };

// Strip react-markdown's own props (`node`, `level` on headings, `depth` on
// lists) before spreading onto DOM elements.
function dom<T extends { node?: unknown; level?: number; depth?: number }>({
  node: _node,
  level: _level,
  depth: _depth,
  ...rest
}: T) {
  return rest;
}

/** True under a Markdown link, so a linked image renders as text there. */
const InsideLink = createContext(false);

/*
 * One element per Markdown construct, styled with v1 type roles rather than
 * @tailwindcss/typography's `prose` (whose v0 config would leak in).
 */
const COMPONENTS = {
  h1: ({ children, ...p }: Props<"h1">) => (
    <h1
      {...dom(p)}
      className="ui:mt-4 ui:mb-2 ui:text-section-title ui:first:mt-0"
    >
      {children}
    </h1>
  ),
  h2: ({ children, ...p }: Props<"h2">) => (
    <h2
      {...dom(p)}
      className="ui:mt-4 ui:mb-2 ui:text-section-title ui:first:mt-0"
    >
      {children}
    </h2>
  ),
  h3: ({ children, ...p }: Props<"h3">) => (
    <h3 {...dom(p)} className="ui:mt-3 ui:mb-1.5 ui:text-body ui:font-semibold">
      {children}
    </h3>
  ),
  h4: ({ children, ...p }: Props<"h4">) => (
    <h4 {...dom(p)} className="ui:mt-3 ui:mb-1.5 ui:text-body ui:font-semibold">
      {children}
    </h4>
  ),
  h5: ({ children, ...p }: Props<"h5">) => (
    <h5
      {...dom(p)}
      className="ui:mt-3 ui:mb-1.5 ui:text-body-small ui:font-semibold"
    >
      {children}
    </h5>
  ),
  h6: ({ children, ...p }: Props<"h6">) => (
    <h6
      {...dom(p)}
      className="ui:mt-3 ui:mb-1.5 ui:text-body-small ui:font-semibold"
    >
      {children}
    </h6>
  ),
  p: (p: Props<"p">) => <p {...dom(p)} className="ui:my-2" />,
  a: ({ href, children, ...p }: Props<"a">) => (
    <a
      {...dom(p)}
      href={href}
      {...(isExternal(href)
        ? { target: "_blank", rel: "noopener noreferrer" }
        : {})}
      className="ui:rounded-sm ui:text-primary ui:underline ui:underline-offset-2 ui:focus-visible:focus-ring"
    >
      <InsideLink.Provider value={true}>{children}</InsideLink.Provider>
    </a>
  ),
  ul: ({ ordered: _o, ...p }: Props<"ul"> & { ordered?: boolean }) => (
    <ul {...dom(p)} className="ui:my-2 ui:list-disc ui:pl-5" />
  ),
  ol: ({ ordered: _o, ...p }: Props<"ol"> & { ordered?: boolean }) => (
    <ol {...dom(p)} className="ui:my-2 ui:list-decimal ui:pl-5" />
  ),
  li: ({
    ordered: _o,
    index: _i,
    checked: _c,
    ...p
  }: Props<"li"> & {
    ordered?: boolean;
    index?: number;
    checked?: boolean | null;
  }) => <li {...dom(p)} className="ui:my-0.5" />,
  blockquote: (p: Props<"blockquote">) => (
    <blockquote
      {...dom(p)}
      className="ui:my-2 ui:border-l-2 ui:border-border ui:pl-3 ui:text-muted-foreground"
    />
  ),
  hr: (p: Props<"hr">) => (
    <hr
      {...dom(p)}
      className="ui:my-4 ui:border-0 ui:border-t ui:border-border"
    />
  ),
  table: (p: Props<"table">) => (
    <div className="ui:my-2 ui:overflow-x-auto">
      <table
        {...dom(p)}
        className="ui:w-full ui:border-collapse ui:text-body-small"
      />
    </div>
  ),
  th: ({ isHeader: _h, ...p }: Props<"th"> & { isHeader?: boolean }) => (
    <th
      {...dom(p)}
      className="ui:border ui:border-border ui:bg-muted ui:px-2 ui:py-1 ui:text-left ui:font-semibold"
    />
  ),
  td: ({ isHeader: _h, ...p }: Props<"td"> & { isHeader?: boolean }) => (
    <td {...dom(p)} className="ui:border ui:border-border ui:px-2 ui:py-1" />
  ),
  // A GFM task-list box: read-only, and named, since its item text is not its label.
  input: ({ checked, type, ...p }: Props<"input">) => (
    <input
      {...dom(p)}
      type={type}
      checked={checked}
      disabled
      readOnly
      aria-label={checked ? "Done" : "Not done"}
      className="ui:mr-1.5 ui:align-middle"
    />
  ),
  // A fenced block arrives as <pre><code>; CodeBlock draws its own frame.
  pre: ({ children }: Props<"pre">) => <>{children}</>,
  code: ({ inline, className, children }: CodeProps) => {
    if (inline) {
      return <InlineCode>{children}</InlineCode>;
    }
    const code = String(children ?? "").replace(/\n$/, "");
    const language = fenceLanguage(className);
    return (
      <CodeBlock
        code={code}
        language={language}
        // Names the header that holds the copy button; plain text has no name.
        title={language === "text" ? undefined : LANGUAGE_NAME[language]}
        className="ui:my-2"
      />
    );
  },
};

// Off by default, an image is a link the reader can choose to follow:
// fetching it on render would let text steered by a document (prompt
// injection) send data to any host in its URL.
// Inside a link (`[![badge](img)](url)`) the image is just text: a second
// anchor would nest `<a>` in `<a>` and hide the link's own target.
function LinkedImage({ alt, src }: Props<"img">): JSX.Element {
  const label = alt ? `Image: ${alt}` : "Image";
  if (useContext(InsideLink)) {
    return <span>{label}</span>;
  }
  return (
    <a
      href={src}
      target="_blank"
      rel="noopener noreferrer"
      className="ui:rounded-sm ui:text-primary ui:underline ui:underline-offset-2 ui:focus-visible:focus-ring"
    >
      {label}
    </a>
  );
}
const LOADED_IMAGE = ({ alt, ...p }: Props<"img">) => (
  <img {...dom(p)} alt={alt ?? ""} className="ui:max-w-full" />
);
const WITH_LINKED_IMAGES = { ...COMPONENTS, img: LinkedImage };
const WITH_LOADED_IMAGES = { ...COMPONENTS, img: LOADED_IMAGE };

export type MarkdownProps = Readonly<{
  /** Markdown source, including GitHub extensions (tables, task lists, strikethrough). */
  children: string;
  /**
   * Loads images inline. Off by default: images show as "Image: alt" links,
   * because text from a model or a document can point an image at any host.
   * Turn it on only for Markdown you author or trust.
   */
  loadImages?: boolean;
  className?: string;
}>;

/**
 * Renders Markdown from models and API Hub descriptions. Raw HTML is dropped,
 * never rendered (no rehype-raw), and link and image URLs go through
 * react-markdown's safe-URL filter, so `javascript:` URLs render inert.
 * External links open in a new tab with `rel="noopener noreferrer"`.
 * Images are links unless `loadImages` is set. Fenced code renders as a
 * CodeBlock.
 */
export function Markdown({
  children,
  loadImages = false,
  className,
}: MarkdownProps): JSX.Element {
  return (
    <div
      data-slot="markdown"
      className={cn(
        "ui:text-body ui:text-foreground ui:break-words",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        // Links get the safe-URL filter by default; images only when asked.
        transformLinkUri={uriTransformer}
        transformImageUri={uriTransformer}
        components={loadImages ? WITH_LOADED_IMAGES : WITH_LINKED_IMAGES}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
