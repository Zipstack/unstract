import { screen, waitFor, within } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { CodeBlock } from "./CodeBlock";
import { InlineCode } from "./InlineCode";

it("renders each line, highlighted with the code tokens", () => {
  const { container } = renderV1(
    <CodeBlock code={'{"a": 1}\n\nnull'} language="json" />,
  );
  const lines = container.querySelectorAll("[data-slot=code-line]");
  expect([...lines].map((l) => l.textContent)).toEqual([
    '{"a": 1}',
    "",
    "null",
  ]);
  expect(container.querySelector(".ui\\:text-code-key")?.textContent).toBe(
    '"a"',
  );
  expect(container.querySelector(".ui\\:text-code-number")?.textContent).toBe(
    "1",
  );
  // Never Prism's own class names, which v0's global Prism theme styles.
  expect(container.innerHTML).not.toMatch(/\btoken\b|language-/);
});

it("names its scrollable region and makes it focusable", async () => {
  const { user, rerender } = renderV1(
    <CodeBlock code="x = 1" language="python" />,
  );
  const region = screen.getByRole("region", { name: "Python code" });
  await user.tab();
  await user.tab();
  expect(document.activeElement).toBe(region);
  rerender(<CodeBlock code="x" title="Request" />);
  expect(screen.getByRole("region", { name: "Request" })).toBeTruthy();
  rerender(<CodeBlock code="x" aria-label="Body" title={<b>Req</b>} />);
  expect(screen.getByRole("region", { name: "Body" })).toBeTruthy();
});

it("shows line numbers only when asked, outside the copied text", () => {
  const { container, rerender } = renderV1(<CodeBlock code={"a\nb"} />);
  expect(container.querySelector("[aria-hidden].ui\\:select-none")).toBeNull();
  rerender(<CodeBlock code={"a\nb"} showLineNumbers />);
  const numbers = container.querySelectorAll(
    "[data-slot=code-line] > [aria-hidden]",
  );
  expect([...numbers].map((n) => n.textContent)).toEqual(["1", "2"]);
});

it("copies the code, and drops the header when there is nothing for it", async () => {
  const { user, container, rerender } = renderV1(
    <CodeBlock code="print(1)" actions={<button type="button">Run</button>} />,
  );
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  const header = container.querySelector("[data-slot=code-block-header]");
  expect(
    within(header as HTMLElement).getByRole("button", { name: "Run" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Copy code" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("print(1)"));
  rerender(<CodeBlock code="x" copyable={false} />);
  expect(container.querySelector("[data-slot=code-block-header]")).toBeNull();
});

it("wraps long lines only when asked", () => {
  const { container, rerender } = renderV1(<CodeBlock code="x" />);
  const content = () =>
    container.querySelector("[data-slot=code-line] > span:last-child");
  expect(content()?.className).toContain("ui:whitespace-pre");
  rerender(<CodeBlock code="x" wrap />);
  expect(content()?.className).toContain("ui:whitespace-pre-wrap");
});

it("passes axe in every mode", async () => {
  for (const theme of ["light", "dark", "unstract"] as const) {
    const { container, unmount } = renderV1(
      <CodeBlock code="a" title="T" showLineNumbers />,
      { theme },
    );
    await expect(container).toHaveNoA11yViolations();
    unmount();
  }
});

it("InlineCode sets mono text as a chip or plain", () => {
  renderV1(
    <p>
      <InlineCode>a</InlineCode>
      <InlineCode variant="plain">2</InlineCode>
    </p>,
  );
  const [chip, plain] = document.querySelectorAll("code");
  expect(chip.className).toContain("ui:font-mono");
  expect(chip.className).toContain("ui:bg-muted");
  expect(plain.className).toContain("ui:font-mono");
  expect(plain.className).not.toContain("ui:bg-muted");
});
