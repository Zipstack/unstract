import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Radio, RadioGroup } from "./RadioGroup";

it("names the group from its label and each radio from its own", () => {
  renderV1(
    <RadioGroup label="Model" defaultValue="gpt">
      <Radio value="gpt" label="GPT" />
      <Radio value="claude" label="Claude" />
      <Radio value="gemini" label="Gemini" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  for (const name of ["GPT", "Claude", "Gemini"]) {
    expect(group).toContainElement(screen.getByRole("radio", { name }));
  }
  expect(screen.getByRole("radio", { name: "GPT" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

it("arrows move the selection and focus", async () => {
  const onValueChange = vi.fn();
  const { user } = renderV1(
    <RadioGroup label="Model" defaultValue="gpt" onValueChange={onValueChange}>
      <Radio value="gpt" label="GPT" />
      <Radio value="claude" label="Claude" />
      <Radio value="gemini" label="Gemini" />
    </RadioGroup>,
  );
  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("radio", { name: "GPT" }),
  );
  // Radix moves focus on a timer and checks the item only while the arrow
  // is still down, as it is in a browser; hold it, then release.
  await user.keyboard("{ArrowDown>}");
  const second = screen.getByRole("radio", { name: "Claude" });
  expect(second).toHaveAttribute("aria-checked", "true");
  expect(document.activeElement).toBe(second);
  expect(onValueChange).toHaveBeenLastCalledWith("claude");
  await user.keyboard("{/ArrowDown}");
});

it("arrows skip a disabled item", async () => {
  const { user } = renderV1(
    <RadioGroup label="Model" defaultValue="gpt">
      <Radio value="gpt" label="GPT" />
      <Radio value="claude" label="Claude" disabled />
      <Radio value="gemini" label="Gemini" />
    </RadioGroup>,
  );
  const second = screen.getByRole("radio", { name: "Claude" });
  expect(second).toHaveAttribute("disabled");
  expect(screen.getByText("Claude")).toHaveAttribute("data-disabled");

  await user.tab();
  await user.keyboard("{ArrowDown>}");
  const third = screen.getByRole("radio", { name: "Gemini" });
  expect(third).toHaveAttribute("aria-checked", "true");
  expect(document.activeElement).toBe(third);
  expect(second).toHaveAttribute("aria-checked", "false");
  await user.keyboard("{/ArrowDown}");
});

it("a radio is described by its description", () => {
  renderV1(
    <RadioGroup label="Model">
      <Radio value="gpt" label="GPT" description="Fast and cheap" />
    </RadioGroup>,
  );
  const radio = screen.getByRole("radio", { name: "GPT" });
  const description = screen.getByText("Fast and cheap");
  expect(description.id).not.toBe("");
  expect(radio.getAttribute("aria-describedby")).toBe(description.id);
});

it("the group is described by its description, keeping the caller's", () => {
  renderV1(
    <RadioGroup
      label="Model"
      description="Used for every prompt"
      aria-describedby="extra"
    >
      <Radio value="gpt" label="GPT" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  const description = screen.getByText("Used for every prompt");
  expect(description.id).not.toBe("");
  const ids = group.getAttribute("aria-describedby")?.split(" ") ?? [];
  expect(ids).toContain("extra");
  expect(ids).toContain(description.id);
});

it("the group takes aria-label when no label is given", () => {
  const { container } = renderV1(
    <RadioGroup aria-label="Model">
      <Radio value="gpt" label="GPT" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  expect(group).not.toHaveAttribute("aria-labelledby");
  expect(group).not.toHaveAttribute("aria-describedby");
  const field = container.querySelector("[data-slot=radio-group-field]");
  expect(field?.children).toHaveLength(1);
  expect(field?.firstElementChild).toBe(group);
});

it("lays the items out in a row when horizontal", () => {
  renderV1(
    <RadioGroup aria-label="Model" orientation="horizontal">
      <Radio value="gpt" label="GPT" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  expect(group).toHaveClass("ui:flex", "ui:flex-wrap", "ui:gap-4");
  expect(group).not.toHaveClass("ui:grid");
  expect(group).toHaveAttribute("aria-orientation", "horizontal");
});

it("does nothing when the group is disabled", async () => {
  const onValueChange = vi.fn();
  const { user } = renderV1(
    <RadioGroup
      label="Model"
      disabled
      defaultValue="gpt"
      onValueChange={onValueChange}
    >
      <Radio value="gpt" label="GPT" />
      <Radio value="claude" label="Claude" />
    </RadioGroup>,
  );
  const radios = screen.getAllByRole("radio");
  for (const radio of radios) {
    expect(radio).toHaveAttribute("disabled");
  }
  expect(screen.getByText("Model")).toHaveAttribute("data-disabled");
  for (const name of ["GPT", "Claude"]) {
    expect(screen.getByText(name)).toHaveAttribute("data-disabled");
  }
  await user.click(screen.getByRole("radio", { name: "Claude" }));
  await user.click(screen.getByText("Claude"));
  expect(screen.getByRole("radio", { name: "GPT" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(onValueChange).not.toHaveBeenCalled();
});

it("is 14px by class", () => {
  renderV1(
    <RadioGroup aria-label="Model" defaultValue="gpt">
      <Radio value="gpt" aria-label="GPT" />
    </RadioGroup>,
  );
  const radio = screen.getByRole("radio", { name: "GPT" });
  expect(radio).toHaveClass("ui:size-3.5", "ui:rounded-full");
  expect(radio.querySelector("[data-slot=radio-indicator]")).not.toBeNull();
});

it("renders only the radio when there is no label or description", () => {
  const { container } = renderV1(
    <RadioGroup aria-label="Model">
      <Radio value="gpt" aria-label="GPT" />
    </RadioGroup>,
  );
  const row = container.querySelector("[data-slot=control-row]");
  expect(row).not.toBeNull();
  const radio = screen.getByRole("radio", { name: "GPT" });
  expect(row?.children).toHaveLength(1);
  const wrapper = row?.firstElementChild;
  expect(wrapper?.tagName).toBe("SPAN");
  expect(wrapper?.children).toHaveLength(1);
  expect(wrapper?.firstElementChild).toBe(radio);
  expect(radio).not.toHaveAttribute("aria-describedby");
});

it("treats a false label and an empty description as absent", () => {
  const { container } = renderV1(
    <RadioGroup label={false} description="" aria-label="Model">
      <Radio value="gpt" label="GPT" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  expect(group).not.toHaveAttribute("aria-labelledby");
  expect(group).not.toHaveAttribute("aria-describedby");
  const field = container.querySelector("[data-slot=radio-group-field]");
  expect(field?.children).toHaveLength(1);
});

it("puts className on the field and keeps the layout classes on the list", () => {
  const { container } = renderV1(
    <RadioGroup aria-label="Model" className="ui:max-w-xs">
      <Radio value="gpt" label="GPT" />
    </RadioGroup>,
  );
  expect(container.querySelector("[data-slot=radio-group-field]")).toHaveClass(
    "ui:max-w-xs",
  );
  const group = screen.getByRole("radiogroup", { name: "Model" });
  expect(group).not.toHaveClass("ui:max-w-xs");
  expect(group).toHaveClass("ui:grid", "ui:gap-2");
});
