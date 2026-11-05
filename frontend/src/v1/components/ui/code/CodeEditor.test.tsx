import { act, screen, waitFor } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { CodeEditor } from "./CodeEditor";

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
  options?: Record<string, unknown>;
};
const seen: MonacoProps[] = [];
vi.mock("@monaco-editor/react", () => ({
  default: (props: MonacoProps) => {
    seen.push(props);
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
      lineNumbers={false}
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
