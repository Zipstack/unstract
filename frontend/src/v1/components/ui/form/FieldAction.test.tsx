import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { FieldAction } from "./FieldAction";

it("is a named button that does not submit its form", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn((event: { preventDefault: () => void }) =>
    event.preventDefault(),
  );
  const onClick = vi.fn();
  render(
    <form onSubmit={onSubmit}>
      <FieldAction label="Copy" onClick={onClick} />
    </form>,
  );
  const button = screen.getByRole("button", { name: "Copy" });
  expect(button.getAttribute("title")).toBe("Copy");
  await user.click(button);
  expect(onClick).toHaveBeenCalledOnce();
  expect(onSubmit).not.toHaveBeenCalled();
});
