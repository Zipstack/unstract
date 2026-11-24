import { fireEvent, screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it } from "vitest";
import { Combobox } from "./Combobox";
import type { SelectOption } from "./options";
import { isInside } from "./shared";

const OPTIONS: readonly SelectOption[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
];

function setup() {
  return renderV1(
    <>
      <Combobox aria-label="C" options={OPTIONS} />
      <button type="button">Elsewhere</button>
    </>,
  );
}

it("counts a target in the frame or in the list as inside, anything else as outside", () => {
  const frame = document.createElement("div");
  const content = document.createElement("div");
  const inFrame = frame.appendChild(document.createElement("input"));
  const inContent = content.appendChild(document.createElement("div"));
  expect(isInside(frame, content, inFrame)).toBe(true);
  expect(isInside(frame, content, inContent)).toBe(true);
  expect(isInside(frame, content, document.body)).toBe(false);
  expect(isInside(frame, content, null)).toBe(false);
});

it("keeps the list open when focus moves from the input into the list", async () => {
  const { user } = setup();
  await user.click(screen.getByRole("combobox", { name: "C" }));
  const list = screen.getByRole("listbox");
  fireEvent.blur(screen.getByRole("combobox", { name: "C" }), {
    relatedTarget: list,
  });
  expect(screen.getByRole("listbox")).toBeTruthy();
});

it("leaves focus where it went when the list closes, not back on the input", async () => {
  const { user } = setup();
  await user.click(screen.getByRole("combobox", { name: "C" }));
  const elsewhere = screen.getByRole("button", { name: "Elsewhere" });
  await user.click(elsewhere);
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(elsewhere);
});

it("aligns the list with the frame's start edge", async () => {
  const { user } = setup();
  await user.click(screen.getByRole("combobox", { name: "C" }));
  const content = screen
    .getByRole("listbox")
    .closest("[data-align]") as HTMLElement;
  expect(content.getAttribute("data-align")).toBe("start");
});
