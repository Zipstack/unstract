import { act, screen, waitFor } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { type ReactNode, useEffect } from "react";
import { expect, it, vi } from "vitest";
import { CodeEditor, EDITOR_LOAD_TIMEOUT_MS } from "./CodeEditor";

/*
 * Monaco's loader fetches its runtime from the CDN, which happy-dom cannot
 * run (and the harness fails any unmocked request), so the editor is a
 * stand-in that records the props the wrapper passes.
 */
type MonacoProps = {
  value?: string;
  defaultValue?: string;
  language?: string;
  theme?: string;
  height?: number | string;
  loading?: ReactNode;
  onChange?: (value: string | undefined) => void;
  onMount?: () => void;
  options?: Record<string, unknown>;
};
const seen: MonacoProps[] = [];
// Whether the stand-in reports a mount, as Monaco does once its runtime loads.
const monaco = vi.hoisted(() => ({ loads: true }));
vi.mock("@monaco-editor/react", () => ({
  default: (props: MonacoProps) => {
    seen.push(props);
    useEffect(() => {
      if (monaco.loads) {
        props.onMount?.();
      }
    }, [props.onMount]);
    if (!monaco.loads) {
      return <>{props.loading}</>;
    }
    return (
      <textarea
        aria-label={String(props.options?.ariaLabel)}
        readOnly={Boolean(props.options?.readOnly)}
        value={props.value ?? props.defaultValue ?? ""}
        onChange={(e) => props.onChange?.(e.target.value)}
      />
    );
  },
}));
const last = () => seen[seen.length - 1];

it("passes value, language, read-only and line numbers through to Monaco", async () => {
  const onChange = vi.fn();
  renderV1(
    <CodeEditor
      aria-label="Prompt"
      value="{}"
      language="bash"
      onChange={onChange}
      height="100%"
    />,
  );
  const editor = await screen.findByRole("textbox", { name: "Prompt" });
  expect(last()).toMatchObject({
    value: "{}",
    language: "shell",
    height: "100%",
    options: { ariaLabel: "Prompt", readOnly: false, lineNumbers: "on" },
  });
  act(() => {
    last().onChange?.(undefined);
  });
  expect(onChange).toHaveBeenLastCalledWith("");
  expect(editor).toBeTruthy();
});

it("is read-only and numberless when asked, and defaults to plain text", async () => {
  renderV1(
    <CodeEditor
      aria-label="Output"
      defaultValue="x"
      readOnly
      showLineNumbers={false}
    />,
  );
  await screen.findByRole("textbox", { name: "Output" });
  expect(last()).toMatchObject({
    defaultValue: "x",
    language: "plaintext",
    height: 320,
    options: { readOnly: true, domReadOnly: true, lineNumbers: "off" },
  });
  expect(last().loading).toBeTruthy();
});

it("follows the v1 theme, including a later switch", async () => {
  renderV1(<CodeEditor aria-label="E" />, { theme: "dark" });
  const editor = await screen.findByRole("textbox", { name: "E" });
  expect(last().theme).toBe("vs-dark");
  const root = editor.closest("[data-theme]") as HTMLElement;
  act(() => root.setAttribute("data-theme", "unstract"));
  await waitFor(() => expect(last().theme).toBe("light"));
});

it("uses the mono font token when the page defines it", async () => {
  renderV1(<CodeEditor aria-label="F" />);
  const editor = await screen.findByRole("textbox", { name: "F" });
  expect(last().options?.fontFamily).toBeUndefined();
  const root = editor.closest("[data-theme]") as HTMLElement;
  // Set on the wrapper itself: happy-dom does not inherit custom properties.
  const wrapper = editor.closest("[data-slot=code-editor]") as HTMLElement;
  wrapper.style.setProperty("--font-mono", '"Geist Mono", monospace');
  act(() => root.setAttribute("data-theme", "light"));
  await waitFor(() =>
    expect(last().options?.fontFamily).toBe('"Geist Mono", monospace'),
  );
});

it("says the editor is slow when Monaco has not mounted, and shows it once it does", async () => {
  monaco.loads = false;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    const { rerender } = renderV1(<CodeEditor aria-label="Late" />);
    expect(await screen.findByText("Loading editor")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(EDITOR_LOAD_TIMEOUT_MS);
    });
    expect(
      screen.getByText("The editor is taking a while to load"),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    // The runtime arrives late: the editor appears and the note goes.
    monaco.loads = true;
    rerender(<CodeEditor aria-label="Late" defaultValue="x" />);
    expect(await screen.findByRole("textbox", { name: "Late" })).toBeTruthy();
    expect(
      screen.queryByText("The editor is taking a while to load"),
    ).toBeNull();
  } finally {
    monaco.loads = true;
    vi.useRealTimers();
  }
});

it("keeps a loaded editor when the timeout passes", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    renderV1(<CodeEditor aria-label="Quick" />);
    await screen.findByRole("textbox", { name: "Quick" });
    act(() => {
      vi.advanceTimersByTime(EDITOR_LOAD_TIMEOUT_MS);
    });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("textbox", { name: "Quick" })).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});
