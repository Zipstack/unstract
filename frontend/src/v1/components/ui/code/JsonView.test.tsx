import { act, screen, waitFor, within } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { largeJson, STATEMENT } from "@v1/test/fixtures/json";
import { expect, it, vi } from "vitest";
import { JsonView, VIRTUALIZE_ABOVE } from "./JsonView";

const items = () => screen.queryAllByRole("treeitem");
const active = () => {
  const tree = screen.getByRole("tree");
  const id = tree.getAttribute("aria-activedescendant");
  return id ? document.getElementById(id)?.textContent : undefined;
};

/** Gives every element a 480×960 box, as a laid-out page would. */
function stubLayout() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, 0, 960, 480),
  );
  for (const [prop, size] of [
    ["offsetHeight", 480],
    ["offsetWidth", 960],
    ["clientHeight", 480],
    ["clientWidth", 960],
    ["scrollHeight", 200_000],
  ] as const) {
    vi.spyOn(HTMLElement.prototype, prop, "get").mockReturnValue(size);
  }
}

it("shows a small document fully expanded as a tree", () => {
  renderV1(<JsonView value={STATEMENT} />);
  const tree = screen.getByRole("tree", { name: "JSON" });
  expect(tree).toBeTruthy();
  // Closing brackets are not tree items.
  expect(items()).toHaveLength(16);
  const rewards = items().find((i) => i.textContent?.includes('"rewards"'));
  expect(rewards?.getAttribute("aria-level")).toBe("2");
  expect(rewards?.getAttribute("aria-expanded")).toBe("true");
  const fees = items().find((i) => i.textContent?.includes('"fees"'));
  expect(fees?.hasAttribute("aria-expanded")).toBe(false);
});

it("starts folded at defaultExpandDepth, with a summary on the folded line", () => {
  renderV1(<JsonView value={STATEMENT} defaultExpandDepth={1} />);
  const rewards = items().find((i) => i.textContent?.includes('"rewards"'));
  expect(rewards?.getAttribute("aria-expanded")).toBe("false");
  expect(rewards?.textContent).toContain("{…},3 keys");
  expect(screen.queryByText(/reward_dollars/)).toBeNull();
});

it("moves, folds and unfolds from the keyboard", async () => {
  const { user } = renderV1(<JsonView value={STATEMENT} />);
  const tree = screen.getByRole("tree");
  act(() => tree.focus());
  expect(active()).toContain("{");
  await user.keyboard("{ArrowDown}");
  expect(active()).toContain('"fees": 0');
  await user.keyboard("{ArrowDown}");
  expect(active()).toContain('"rewards"');
  // Left folds an open container, Right unfolds it, Right again enters it.
  await user.keyboard("{ArrowLeft}");
  expect(screen.queryByText(/reward_dollars/)).toBeNull();
  await user.keyboard("{ArrowRight}");
  expect(screen.queryByText(/"reward_dollars"/)).toBeTruthy();
  await user.keyboard("{ArrowRight}");
  expect(active()).toContain('"reward_dollars"');
  // Left on a leaf goes to its parent.
  await user.keyboard("{ArrowLeft}");
  expect(active()).toContain('"rewards"');
  // Enter and Space toggle.
  await user.keyboard("{Enter}");
  expect(screen.queryByText(/reward_dollars/)).toBeNull();
  await user.keyboard(" ");
  expect(screen.queryByText(/"reward_dollars"/)).toBeTruthy();
  // Down skips closing brackets; Up comes back over them.
  await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{ArrowDown}");
  expect(active()).toContain('"website"');
  await user.keyboard("{ArrowUp}");
  expect(active()).toContain('"reward_dollars_as_of_date"');
  await user.keyboard("{End}");
  expect(active()).toContain('"amount": 13');
  await user.keyboard("{Home}");
  expect(active()).toContain("{");
  // Up at the top and Left on the root stay put; other keys are ignored.
  await user.keyboard("{ArrowUp}{ArrowLeft}{ArrowLeft}a");
  expect(active()).toBe("1{…}6 keys");
});

it("puts the active row on the folded container when its row is hidden", async () => {
  const { user } = renderV1(<JsonView value={STATEMENT} />);
  const tree = screen.getByRole("tree");
  act(() => tree.focus());
  await user.keyboard("{ArrowDown}{ArrowDown}{ArrowRight}{ArrowRight}");
  expect(active()).toContain('"reward_dollars"');
  await user.click(screen.getByRole("button", { name: "Collapse all" }));
  act(() => tree.focus());
  expect(active()).toContain('"rewards"');
});

it("toggles from the chevron and makes a clicked row active", async () => {
  const { user, container } = renderV1(<JsonView value={STATEMENT} />);
  const rewards = items().find((i) => i.textContent?.includes('"rewards"'));
  const chevron = rewards?.querySelector("[data-slot=json-toggle]");
  await user.click(chevron as Element);
  expect(rewards?.getAttribute("aria-expanded")).toBe("false");
  expect(document.activeElement).toBe(screen.getByRole("tree"));
  expect(active()).toContain('"rewards"');
  expect(container.querySelector("[data-active]")?.textContent).toContain(
    '"rewards"',
  );
  // A click elsewhere on the row only selects it.
  const fees = items().find((i) => i.textContent?.includes('"fees"'));
  await user.click(fees as Element);
  expect(active()).toContain('"fees"');
  expect(rewards?.getAttribute("aria-expanded")).toBe("false");
});

it("expands and collapses everything from the toolbar", async () => {
  const { user } = renderV1(<JsonView value={STATEMENT} />);
  await user.click(screen.getByRole("button", { name: "Collapse all" }));
  // The root stays open; every container under it folds.
  expect(items()).toHaveLength(7);
  await user.click(screen.getByRole("button", { name: "Expand all" }));
  expect(items()).toHaveLength(16);
});

it("switches to raw text, uncontrolled or controlled", async () => {
  const onModeChange = vi.fn();
  const { user, rerender } = renderV1(
    <JsonView value={STATEMENT} onModeChange={onModeChange} />,
  );
  await user.click(screen.getByRole("button", { name: "Raw" }));
  expect(onModeChange).toHaveBeenCalledWith("raw");
  expect(screen.queryByRole("tree")).toBeNull();
  const region = screen.getByRole("region", { name: "JSON" });
  expect(region.textContent).toContain('"reward_dollars": 1087.93');
  expect(screen.queryByRole("button", { name: "Expand all" })).toBeNull();
  expect(
    screen.getByRole("button", { name: "Raw" }).getAttribute("aria-pressed"),
  ).toBe("true");

  rerender(
    <JsonView value={STATEMENT} mode="tree" onModeChange={onModeChange} />,
  );
  await user.click(screen.getByRole("button", { name: "Raw" }));
  expect(onModeChange).toHaveBeenLastCalledWith("raw");
  // Controlled: stays a tree until the parent changes `mode`.
  expect(screen.getByRole("tree")).toBeTruthy();
});

it("copies the pretty-printed JSON", async () => {
  const { user } = renderV1(<JsonView text={'{"a":[1,{"b":null}]}'} />);
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  await user.click(screen.getByRole("button", { name: "Copy JSON" }));
  await waitFor(() =>
    expect(writeText).toHaveBeenCalledWith(
      JSON.stringify({ a: [1, { b: null }] }, null, 2),
    ),
  );
});

it("shows invalid text as an error with the text as it came", async () => {
  const { user } = renderV1(<JsonView text={'{"a": 1,,}'} />);
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("Invalid JSON");
  const raw = screen.getByRole("region", { name: "JSON (as received)" });
  expect(raw.querySelector("code")?.textContent).toContain('{"a": 1,,}');
  expect(screen.queryByRole("button", { name: "Raw" })).toBeNull();
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  await user.click(screen.getByRole("button", { name: "Copy JSON" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith('{"a": 1,,}'));
});

it("shows a value it cannot serialise as an error, and nothing as 'No data'", () => {
  const { rerender } = renderV1(<JsonView value={{ n: BigInt(1) }} />);
  expect(screen.getByRole("alert").textContent).toMatch(/BigInt/i);
  rerender(<JsonView value={undefined} />);
  expect(screen.getByText("No data")).toBeTruthy();
});

it("resets folding when the document changes", async () => {
  const { user, rerender } = renderV1(<JsonView value={STATEMENT} />);
  await user.click(screen.getByRole("button", { name: "Collapse all" }));
  expect(items()).toHaveLength(7);
  rerender(<JsonView value={{ ...STATEMENT, extra: [1] }} />);
  expect(items()).toHaveLength(18);
});

it("hides the toolbar parts that are turned off", () => {
  const { container } = renderV1(
    <JsonView
      value={1}
      copyable={false}
      showModeToggle={false}
      showLineNumbers={false}
      title="Result"
      actions={<button type="button">Find</button>}
    />,
  );
  const toolbar = container.querySelector(
    "[data-slot=json-view-toolbar]",
  ) as HTMLElement;
  expect(
    within(toolbar).queryByRole("button", { name: "Copy JSON" }),
  ).toBeNull();
  expect(within(toolbar).queryByRole("group")).toBeNull();
  expect(within(toolbar).getByText("Result")).toBeTruthy();
  expect(within(toolbar).getByRole("button", { name: "Find" })).toBeTruthy();
  expect(container.querySelector(".ui\\:select-none")).toBeNull();
});

it("passes axe as a tree and as raw text, in every mode", async () => {
  for (const theme of ["light", "dark", "unstract"] as const) {
    for (const defaultMode of ["tree", "raw"] as const) {
      const { container, unmount } = renderV1(
        <JsonView value={STATEMENT} defaultMode={defaultMode} />,
        { theme },
      );
      await expect(container).toHaveNoA11yViolations();
      unmount();
    }
  }
});

it("stays responsive with 5,000 lines: renders a window, folds and unfolds fast", async () => {
  stubLayout();
  const value = largeJson(5000);
  const started = performance.now();
  const { user, container } = renderV1(<JsonView value={value} />);
  const rendered = () =>
    container.querySelectorAll("[data-slot=json-line]").length;
  // Opens to depth 2, still far more lines than the virtualisation
  // threshold, but only the rows in view (plus overscan) are in the DOM.
  await waitFor(() => expect(rendered()).toBeGreaterThan(0));
  expect(rendered()).toBeLessThan(VIRTUALIZE_ABOVE / 3);

  await user.click(screen.getByRole("button", { name: "Expand all" }));
  expect(rendered()).toBeLessThan(VIRTUALIZE_ABOVE / 3);
  await user.click(screen.getByRole("button", { name: "Collapse all" }));
  expect(items()[1].getAttribute("aria-expanded")).toBe("false");
  expect(rendered()).toBeLessThan(VIRTUALIZE_ABOVE / 3);
  await user.click(screen.getByRole("button", { name: "Raw" }));
  expect(rendered()).toBeLessThan(VIRTUALIZE_ABOVE / 3);
  // Generous for CI: render, expand all, collapse all and switch to raw.
  expect(performance.now() - started).toBeLessThan(3000);

  // The window follows the keyboard to the last line.
  await user.click(screen.getByRole("button", { name: "Tree" }));
  await user.click(screen.getByRole("button", { name: "Expand all" }));
  const tree = screen.getByRole("tree");
  act(() => tree.focus());
  await user.keyboard("{End}");
  await waitFor(() => expect(tree.scrollTop).toBeGreaterThan(0));
  // happy-dom scrolls but fires no scroll event; a browser does.
  act(() => {
    tree.dispatchEvent(new Event("scroll"));
  });
  // Line 4,999 is the last item; 5,000 is the closing bracket.
  await waitFor(() => expect(active()).toMatch(/^4999\s+5$/));
});
