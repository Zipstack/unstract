import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { createRef } from "react";
import { expect, it } from "vitest";
import { Checkbox } from "./Checkbox";
import { Radio, RadioGroup } from "./RadioGroup";
import { Slider } from "./Slider";
import { Switch } from "./Switch";

/*
 * Where a caller's `ref` and `id` land: on the focusable control for a
 * Checkbox, Switch or Radio; on the radiogroup for a RadioGroup; on the
 * slider's group root (not a thumb) for a Slider. Never on the row or field.
 */

it("puts a Checkbox's ref and id on the checkbox", () => {
  const ref = createRef<HTMLButtonElement>();
  renderV1(<Checkbox ref={ref} id="c" label="C" />);
  const box = screen.getByRole("checkbox", { name: "C" });
  expect(ref.current).toBe(box);
  expect(box).toHaveAttribute("id", "c");
});

it("puts a Switch's ref and id on the switch", () => {
  const ref = createRef<HTMLButtonElement>();
  renderV1(<Switch ref={ref} id="s" label="S" />);
  const control = screen.getByRole("switch", { name: "S" });
  expect(ref.current).toBe(control);
  expect(control).toHaveAttribute("id", "s");
});

it("puts a Radio's ref and id on the radio, and a RadioGroup's on the group", () => {
  const groupRef = createRef<HTMLDivElement>();
  const radioRef = createRef<HTMLButtonElement>();
  renderV1(
    <RadioGroup ref={groupRef} id="g" label="G">
      <Radio ref={radioRef} id="r" value="r" label="R" />
    </RadioGroup>,
  );
  const group = screen.getByRole("radiogroup", { name: "G" });
  const radio = screen.getByRole("radio", { name: "R" });
  expect(groupRef.current).toBe(group);
  expect(group).toHaveAttribute("id", "g");
  expect(radioRef.current).toBe(radio);
  expect(radio).toHaveAttribute("id", "r");
});

it("puts a Slider's ref and id on the group root, not a thumb", () => {
  const ref = createRef<HTMLSpanElement>();
  const { container } = renderV1(
    <Slider ref={ref} id="v" label="V" defaultValue={[5]} />,
  );
  const root = container.querySelector("[data-slot=slider]");
  expect(root).toBe(screen.getByRole("group", { name: "V" }));
  expect(ref.current).toBe(root);
  expect(root).toHaveAttribute("id", "v");
  expect(screen.getByRole("slider", { name: "V" })).not.toHaveAttribute("id");
});
