import {
  InlineAlert,
  Skeleton,
  SkeletonBlock,
} from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import type { CodeLanguage } from "@v1/lib/code/highlight";
import {
  Component,
  type JSX,
  lazy,
  type ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
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
// One import shared by the lazy editor and the loader watch below.
let monacoModule: Promise<typeof import("@monaco-editor/react")> | undefined;
function importMonaco() {
  monacoModule ??= import("@monaco-editor/react");
  return monacoModule;
}
const MonacoEditor = lazy(importMonaco);

/*
 * Monaco has one theme per page: `monaco.editor.setTheme` restyles every
 * editor on screen, and @monaco-editor/react applies an editor's theme when
 * it is created and whenever its `theme` prop changes. v1 and v0 never share
 * a page (the version switch renders one tree or the other, UN-4271), and
 * v0's one editor sets its own theme when it mounts, so a v1 editor cannot
 * leave v0 restyled. Should both ever render together, the last to mount or
 * change wins. The names below mark the themes as v1's; they inherit Monaco's
 * own, and defining them changes no other editor.
 */
const V1_THEMES = { light: "unstract-v1-light", dark: "unstract-v1-dark" };
function defineV1Themes(monaco: {
  editor: {
    defineTheme: (
      name: string,
      data: {
        base: "vs" | "vs-dark";
        inherit: boolean;
        rules: [];
        colors: Record<string, string>;
      },
    ) => void;
  };
}): void {
  const theme = { inherit: true, rules: [] as [], colors: {} };
  monaco.editor.defineTheme(V1_THEMES.light, { ...theme, base: "vs" });
  monaco.editor.defineTheme(V1_THEMES.dark, { ...theme, base: "vs-dark" });
}

/**
 * How long the editor may stay on its skeleton before it says it is taking a
 * while. The editor stays mounted, so a slow load that finishes later still
 * shows. A load that fails outright (a blocked CDN) is caught separately, by
 * watching the loader: @monaco-editor/react itself only logs it.
 */
export const EDITOR_LOAD_TIMEOUT_MS = 15_000;

/** Turns an error in the editor (such as a failed chunk) into the editor's own error state instead of unmounting the page. */
class LoadBoundary extends Component<
  Readonly<{ onError: () => void; children: ReactNode }>,
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

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
  showLineNumbers?: boolean;
  /** Editor height: pixels, or any CSS length (`"100%"` inside a sized parent). Default 320. */
  height?: number | string;
  /** Names the editor for screen readers. Required: an editor has no visible label of its own. */
  "aria-label": string;
  className?: string;
}>;

/**
 * An editable code field. Engine-agnostic props over Monaco
 * (@monaco-editor/react), which loads on first render behind a skeleton.
 * After EDITOR_LOAD_TIMEOUT_MS without it a note says it is taking a while
 * (the editor still appears if it loads), and an error in the editor shows
 * an error in its place.
 * Follows the v1 theme (light or dark) and the mono font token.
 */
export function CodeEditor({
  value,
  defaultValue,
  onChange,
  language = "text",
  readOnly = false,
  showLineNumbers = true,
  height = 320,
  "aria-label": ariaLabel,
  className,
}: CodeEditorProps): JSX.Element {
  const ref = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState({ dark: false, font: "" });
  const [load, setLoad] = useState<"loading" | "slow" | "ready" | "failed">(
    "loading",
  );
  // Monaco reapplies `options` and re-subscribes its change listener whenever
  // they change identity, so both stay stable across parent re-renders. The
  // latest onChange is kept in a ref, updated after commit (as DocumentViewer
  // does) so a render React throws away cannot leave it stale.
  const latestOnChange = useRef(onChange);
  useLayoutEffect(() => {
    latestOnChange.current = onChange;
  }, [onChange]);
  const handleChange = useCallback(
    (next: string | undefined) => latestOnChange.current?.(next ?? ""),
    [],
  );
  const handleMount = () => setLoad("ready");
  const options = useMemo(
    () => ({
      ariaLabel,
      readOnly,
      domReadOnly: readOnly,
      lineNumbers: showLineNumbers ? ("on" as const) : ("off" as const),
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      automaticLayout: true,
      fontSize: 12,
      ...(theme.font ? { fontFamily: theme.font } : {}),
    }),
    [ariaLabel, readOnly, showLineNumbers, theme.font],
  );

  useEffect(() => {
    const timer = setTimeout(
      () => setLoad((now) => (now === "loading" ? "slow" : now)),
      EDITOR_LOAD_TIMEOUT_MS,
    );
    let live = true;
    // Joins the loader's one shared load (init, never config: see above) to
    // learn when the runtime cannot load at all.
    importMonaco()
      .then(({ loader }) => loader.init())
      .catch(() => {
        if (live) {
          setLoad("failed");
        }
      });
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, []);

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
      {load === "failed" ? (
        <InlineAlert title="The editor could not load" className="ui:m-2">
          Reload the page to try again.
        </InlineAlert>
      ) : null}
      {load === "slow" ? (
        <InlineAlert
          kind="warning"
          title="The editor is taking a while to load"
          className="ui:m-2"
        >
          Check your connection. If it does not appear, reload the page.
        </InlineAlert>
      ) : null}
      {load === "failed" ? null : (
        <LoadBoundary onError={() => setLoad("failed")}>
          <Suspense fallback={loading}>
            <MonacoEditor
              value={value}
              defaultValue={defaultValue}
              language={MONACO_LANGUAGE[language]}
              height={height}
              theme={theme.dark ? V1_THEMES.dark : V1_THEMES.light}
              beforeMount={defineV1Themes}
              loading={loading}
              onMount={handleMount}
              onChange={handleChange}
              options={options}
            />
          </Suspense>
        </LoadBoundary>
      )}
    </div>
  );
}
