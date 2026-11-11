import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { FieldAction } from "./FieldAction";

it("is a named button that does not submit its form", async () => {
  const onSubmit = vi.fn((event: { preventDefault: () => void }) =>
    event.preventDefault(),
  );
  const onClick = vi.fn();
  const { user } = renderV1(
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
