import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type JSX, useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { Field } from "./Field";
import { PromptTextarea } from "./PromptTextarea";

afterEach(() => vi.unstubAllGlobals());

function setup(onSubmit = vi.fn()) {
  render(<PromptTextarea aria-label="Prompt" onSubmit={onSubmit} />);
  return {
    onSubmit,
    textarea: screen.getByLabelText("Prompt") as HTMLTextAreaElement,
  };
}

it("submits the text on Enter without inserting a line break", async () => {
  const user = userEvent.setup();
  const { onSubmit, textarea } = setup();
  await user.type(textarea, "Summarise{Enter}");
  expect(onSubmit).toHaveBeenCalledExactlyOnceWith("Summarise");
  expect(textarea.value).toBe("Summarise");
});

it("inserts a line break on Shift+Enter and does not submit", async () => {
  const user = userEvent.setup();
  const { onSubmit, textarea } = setup();
  await user.type(textarea, "one{Shift>}{Enter}{/Shift}two");
  expect(onSubmit).not.toHaveBeenCalled();
  expect(textarea.value).toBe("one\ntwo");
});

it("does not submit an Enter that ends an IME composition", () => {
  const { onSubmit, textarea } = setup();
  fireEvent.keyDown(textarea, { key: "Enter", isComposing: true });
  // Safari: composition already ended, only keyCode 229 marks it.
  fireEvent.keyDown(textarea, { key: "Enter", keyCode: 229 });
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.keyDown(textarea, { key: "Enter" });
  expect(onSubmit).toHaveBeenCalledOnce();
});

it("lets the caller's onKeyDown cancel the submit", () => {
  const onSubmit = vi.fn();
  render(
    <PromptTextarea
      aria-label="Prompt"
      onSubmit={onSubmit}
      onKeyDown={(event) => event.preventDefault()}
    />,
  );
  fireEvent.keyDown(screen.getByLabelText("Prompt"), { key: "Enter" });
  expect(onSubmit).not.toHaveBeenCalled();
});

it("inserts a line break on Enter when there is no onSubmit", async () => {
  const user = userEvent.setup();
  render(<PromptTextarea aria-label="Prompt" />);
  const textarea = screen.getByLabelText("Prompt") as HTMLTextAreaElement;
  await user.type(textarea, "a{Enter}b");
  expect(textarea.value).toBe("a\nb");
});

it("starts at 104, grows with content, and scrolls past its maximum", () => {
  const { textarea } = setup();
  expect(textarea.parentElement?.className).toContain("ui:min-h-26");
  expect(textarea.className).toContain("ui:field-sizing-content");
  expect(textarea.className).toContain("ui:max-h-60");
  expect(textarea.className).toContain("ui:overflow-y-auto");
});

it("sizes itself from scrollHeight where field-sizing is unsupported", () => {
  vi.stubGlobal("CSS", { supports: () => false });
  const { textarea } = setup();
  Object.defineProperty(textarea, "scrollHeight", { value: 180 });
  fireEvent.input(textarea, { target: { value: "long text" } });
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("180px");
});

/** Makes scrollHeight follow the text, as a laid-out textarea would. */
function measureByLength(textarea: HTMLTextAreaElement) {
  Object.defineProperty(textarea, "scrollHeight", {
    configurable: true,
    get: () => (textarea.value === "" ? 104 : 104 + textarea.value.length),
  });
}

it("re-fits a controlled value cleared after submit, without an input event", async () => {
  vi.stubGlobal("CSS", { supports: () => false });
  const user = userEvent.setup();
  function Controlled() {
    const [value, setValue] = useState("");
    return (
      <PromptTextarea
        aria-label="Prompt"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onSubmit={() => setValue("")}
      />
    );
  }
  render(<Controlled />);
  const textarea = screen.getByLabelText("Prompt") as HTMLTextAreaElement;
  measureByLength(textarea);
  await user.type(textarea, "twelve chars");
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("116px");
  await user.keyboard("{Enter}");
  expect(textarea.value).toBe("");
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("104px");
});

it("re-fits an uncontrolled value after its form resets", async () => {
  vi.stubGlobal("CSS", { supports: () => false });
  render(
    <form>
      <PromptTextarea aria-label="Prompt" defaultValue="" />
    </form>,
  );
  const textarea = screen.getByLabelText("Prompt") as HTMLTextAreaElement;
  measureByLength(textarea);
  fireEvent.input(textarea, { target: { value: "abcd" } });
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("108px");
  textarea.form?.reset();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  expect(textarea.value).toBe("");
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("104px");
});

it("keeps the height automatic while there is no layout to measure", () => {
  vi.stubGlobal("CSS", { supports: () => false });
  const { textarea } = setup();
  Object.defineProperty(textarea, "scrollHeight", { value: 0 });
  fireEvent.input(textarea, { target: { value: "hidden" } });
  expect(textarea.style.getPropertyValue("--prompt-height")).toBe("");
});

it.each([
  ["prop", (node: JSX.Element) => node, { readOnly: true }],
  [
    "Field",
    (node: JSX.Element) => (
      <Field label="Prompt" readOnly>
        {node}
      </Field>
    ),
    {},
  ],
])("does not submit when read-only by %s", (_, wrap, props) => {
  const onSubmit = vi.fn();
  render(
    wrap(<PromptTextarea aria-label="Prompt" onSubmit={onSubmit} {...props} />),
  );
  fireEvent.keyDown(screen.getByLabelText("Prompt"), { key: "Enter" });
  expect(onSubmit).not.toHaveBeenCalled();
});
