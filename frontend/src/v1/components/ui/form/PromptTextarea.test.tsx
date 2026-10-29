import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
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
