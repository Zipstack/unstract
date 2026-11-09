import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { Chip } from "./Chip";

it("renders the label with a remove button named after it", async () => {
  const onRemove = vi.fn();
  const { user } = renderV1(<Chip label="GPT-4o" onRemove={onRemove} />);
  const chip = document.querySelector('[data-slot="chip"]');
  expect(chip?.textContent).toBe("GPT-4o");
  const remove = screen.getByRole("button", { name: "Remove GPT-4o" });
  expect(remove.getAttribute("type")).toBe("button");
  await user.click(remove);
  expect(onRemove).toHaveBeenCalledTimes(1);
});

it("disables the remove button when the chip is disabled", async () => {
  const onRemove = vi.fn();
  const { user } = renderV1(
    <Chip label="GPT-4o" onRemove={onRemove} disabled />,
  );
  const remove = screen.getByRole("button", { name: "Remove GPT-4o" });
  expect((remove as HTMLButtonElement).disabled).toBe(true);
  await user.click(remove);
  expect(onRemove).not.toHaveBeenCalled();
});

it("has no remove button without onRemove", () => {
  renderV1(<Chip label="GPT-4o" />);
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.getByText("GPT-4o")).toBeTruthy();
});
