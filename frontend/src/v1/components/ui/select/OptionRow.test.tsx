import { fireEvent, screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { Star } from "lucide-react";
import { expect, it, vi } from "vitest";
import { OptionRow } from "./OptionRow";
import type { SelectOption } from "./options";

const GPT: SelectOption = { value: "gpt-4o", label: "GPT-4o" };

it("renders an option named by its label, without a description", () => {
  renderV1(<OptionRow id="o1" option={GPT} selected={false} active={false} />);
  const row = screen.getByRole("option", { name: "GPT-4o" });
  expect(row.id).toBe("o1");
  expect(row.getAttribute("data-slot")).toBe("option");
  expect(row.getAttribute("aria-selected")).toBe("false");
  expect(row.textContent).toBe("GPT-4o");
  expect(row.className).toContain("ui:h-8");
  expect(row.className).not.toContain("ui:h-12");
});

it("renders the description and the taller row when one is given", () => {
  renderV1(
    <OptionRow
      id="o1"
      option={{ ...GPT, description: "OpenAI omni model" }}
      selected={false}
      active={false}
    />,
  );
  const row = screen.getByRole("option", { name: /GPT-4o/ });
  expect(screen.getByText("OpenAI omni model")).toBeTruthy();
  expect(row.className).toContain("ui:h-12");
  expect(row.className).not.toContain("ui:h-8");
});

it("draws the check only on the selected option", () => {
  const { rerender } = renderV1(
    <OptionRow id="o1" option={GPT} selected={false} active={false} />,
  );
  expect(document.querySelector("svg.lucide-check")).toBeNull();
  rerender(<OptionRow id="o1" option={GPT} selected active={false} />);
  const row = screen.getByRole("option", { name: "GPT-4o" });
  expect(row.getAttribute("aria-selected")).toBe("true");
  expect(row.querySelector("svg.lucide-check")).not.toBeNull();
});

it("renders the leading slot only when given", () => {
  const { rerender } = renderV1(
    <OptionRow id="o1" option={GPT} selected={false} active={false} />,
  );
  expect(document.querySelector('[data-slot="option-leading"]')).toBeNull();
  rerender(
    <OptionRow
      id="o1"
      option={{ ...GPT, leading: <Star aria-hidden /> }}
      selected={false}
      active={false}
    />,
  );
  const leading = document.querySelector('[data-slot="option-leading"]');
  expect(leading?.querySelector("svg.lucide-star")).not.toBeNull();
});

it("marks the active row with data-active", () => {
  const { rerender } = renderV1(
    <OptionRow id="o1" option={GPT} selected={false} active={false} />,
  );
  const row = screen.getByRole("option");
  expect(row.hasAttribute("data-active")).toBe(false);
  rerender(<OptionRow id="o1" option={GPT} selected={false} active />);
  expect(row.getAttribute("data-active")).toBe("");
});

it("sets aria-disabled only on a disabled option", () => {
  const { rerender } = renderV1(
    <OptionRow id="o1" option={GPT} selected={false} active={false} />,
  );
  const row = screen.getByRole("option");
  expect(row.hasAttribute("aria-disabled")).toBe(false);
  expect(row.className).not.toContain("ui:pointer-events-none");
  expect(row.className).not.toContain("ui:opacity-50");
  rerender(
    <OptionRow
      id="o1"
      option={{ ...GPT, disabled: true }}
      selected={false}
      active={false}
    />,
  );
  expect(row.getAttribute("aria-disabled")).toBe("true");
  expect(row.className).toContain("ui:pointer-events-none");
  expect(row.className).toContain("ui:opacity-50");
});

it("ignores synthetic clicks and mouse moves on a disabled option", () => {
  const onSelect = vi.fn();
  const onActivate = vi.fn();
  renderV1(
    <OptionRow
      id="o1"
      option={{ ...GPT, disabled: true }}
      selected={false}
      active={false}
      onSelect={onSelect}
      onActivate={onActivate}
    />,
  );
  const row = screen.getByRole("option");
  fireEvent.click(row);
  fireEvent.mouseMove(row);
  expect(onSelect).not.toHaveBeenCalled();
  expect(onActivate).not.toHaveBeenCalled();
});

it("selects an enabled option on a synthetic click", () => {
  const onSelect = vi.fn();
  renderV1(
    <OptionRow
      id="o1"
      option={GPT}
      selected={false}
      active={false}
      onSelect={onSelect}
    />,
  );
  fireEvent.click(screen.getByRole("option"));
  expect(onSelect).toHaveBeenCalledTimes(1);
});

it("calls onSelect on click and onActivate on mouse move", async () => {
  const onSelect = vi.fn();
  const onActivate = vi.fn();
  const { user } = renderV1(
    <OptionRow
      id="o1"
      option={GPT}
      selected={false}
      active={false}
      onSelect={onSelect}
      onActivate={onActivate}
    />,
  );
  const row = screen.getByRole("option");
  fireEvent.mouseMove(row);
  expect(onActivate).toHaveBeenCalledTimes(1);
  await user.click(row);
  expect(onSelect).toHaveBeenCalledTimes(1);
});

it("prevents the mousedown default so a combobox input keeps focus", () => {
  renderV1(<OptionRow id="o1" option={GPT} selected={false} active={false} />);
  const event = new MouseEvent("mousedown", {
    bubbles: true,
    cancelable: true,
  });
  screen.getByRole("option").dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
});
