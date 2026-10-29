import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ViewerStatus, type ViewerStatusState } from "./ViewerStatus";

function setup(state: ViewerStatusState) {
  const onRetry = vi.fn();
  const onSubmitPassword = vi.fn();
  render(
    <ViewerStatus
      state={state}
      onRetry={onRetry}
      onSubmitPassword={onSubmitPassword}
    />,
  );
  return { onRetry, onSubmitPassword };
}

it("announces loading politely", () => {
  setup({ status: "loading" });
  expect(screen.getByRole("status").textContent).toContain("Loading document");
});

it("shows the empty state", () => {
  setup({ status: "empty" });
  expect(screen.getByText("No document")).toBeTruthy();
});

it("explains an unsupported file without offering Retry", () => {
  setup({ status: "unsupported" });
  expect(screen.getByRole("alert").textContent).toContain("can't be previewed");
  expect(screen.queryByRole("button")).toBeNull();
});

it("shows the failure message and retries on click", async () => {
  const { onRetry } = setup({ status: "failed", message: "Network error" });
  expect(screen.getByRole("alert").textContent).toContain("Network error");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

it("submits a typed password, and not an empty one", async () => {
  const { onSubmitPassword } = setup({ status: "password", incorrect: false });
  await userEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(onSubmitPassword).not.toHaveBeenCalled();

  await userEvent.type(screen.getByLabelText("Password"), "secret{Enter}");
  expect(onSubmitPassword).toHaveBeenCalledWith("secret");
});

it("marks a wrong password on the field", () => {
  setup({ status: "password", incorrect: true });
  const field = screen.getByLabelText("Password");
  expect(field.getAttribute("aria-invalid")).toBe("true");
  const description = field.getAttribute("aria-describedby") ?? "";
  expect(document.getElementById(description)?.textContent).toBe(
    "That password is incorrect.",
  );
});
