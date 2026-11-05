import { Skeleton, SkeletonBlock } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import type { CodeLanguage } from "@v1/lib/code/highlight";
import {
  type JSX,
  lazy,
  Suspense,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

/*
 * Monaco, lazy-loaded so it never lands in the main chunk.
 *
 * The Monaco runtime comes from @monaco-editor/loader's default CDN
 * (cdn.jsdelivr.net), exactly as v0's editors load it; nginx's CSP already
 * allows it. v1 must never call `loader.config()`: the loader is a module
 * singleton shared with v0's editors in the same bundle, so configuring it
 * here would change v0.
 */
const MonacoEditor = lazy(() => import("@monaco-editor/react"));

// Our grammar names → Monaco's language ids.
const MONACO_LANGUAGE: Readonly<Record<CodeLanguage, string>> = {
  json: "json",
  bash: "shell",
  python: "python",
  javascript: "javascript",
  typescript: "typescript",
  yaml: "yaml",
  markdown: "markdown",
  text: "plaintext",
};

/** The v1 mode around `element`, and the mono font token's value there. */
function readTheme(element: HTMLElement): { dark: boolean; font: string } {
  const root = element.closest("[data-theme]");
  return {
    dark: root?.getAttribute("data-theme") === "dark",
    font: getComputedStyle(element).getPropertyValue("--font-mono").trim(),
  };
}

export type CodeEditorProps = Readonly<{
  /** Controlled value. */
  value?: string;
  /** Starting value when uncontrolled. */
  defaultValue?: string;
  /** Called with the full text on every edit. */
  onChange?: (value: string) => void;
  language?: CodeLanguage;
  readOnly?: boolean;
  /** Shows the line-number gutter (default on). */
  lineNumbers?: boolean;
  /** Editor height: pixels, or any CSS length (`"100%"` inside a sized parent). Default 320. */
  height?: number | string;
  /** Names the editor for screen readers. Required: an editor has no visible label of its own. */
  "aria-label": string;
  className?: string;
}>;

/**
 * An editable code field. Engine-agnostic props over Monaco
 * (@monaco-editor/react), which loads on first render behind a skeleton.
 * Follows the v1 theme (light or dark) and the mono font token.
 */
export function CodeEditor({
  value,
  defaultValue,
  onChange,
  language = "text",
  readOnly = false,
  lineNumbers = true,
  height = 320,
  "aria-label": ariaLabel,
  className,
}: CodeEditorProps): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState({ dark: false, font: "" });

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    setTheme(readTheme(element));
    const root = element.closest("[data-theme]");
    if (!root) {
      return;
    }
    // ThemeProvider switches modes by rewriting data-theme on the v1 root.
    const observer = new MutationObserver(() => setTheme(readTheme(element)));
    observer.observe(root, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  const loading = (
    <Skeleton label="Loading editor" className="ui:p-3">
      <SkeletonBlock />
    </Skeleton>
  );

  return (
    <div
      ref={ref}
      data-slot="code-editor"
      className={cn(
        "ui:overflow-hidden ui:rounded-lg ui:border ui:border-input ui:bg-card ui:focus-within:focus-ring",
        className,
      )}
    >
      <Suspense fallback={loading}>
        <MonacoEditor
          value={value}
          defaultValue={defaultValue}
          language={MONACO_LANGUAGE[language]}
          height={height}
          theme={theme.dark ? "vs-dark" : "light"}
          loading={loading}
          onChange={(next) => onChange?.(next ?? "")}
          options={{
            ariaLabel,
            readOnly,
            domReadOnly: readOnly,
            lineNumbers: lineNumbers ? "on" : "off",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            fontSize: 12,
            ...(theme.font ? { fontFamily: theme.font } : {}),
          }}
        />
      </Suspense>
    </div>
  );
}
