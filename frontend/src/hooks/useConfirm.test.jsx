import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useConfirm } from "@/hooks/useConfirm";

/** Explicit no-op: some cases do not assert on the resolved value. */
const noop = () => undefined;

function Harness({ options, onResult }) {
  const { confirm, confirmDialog } = useConfirm();
  return (
    <>
      <button
        type="button"
        onClick={async () => {
          onResult(await confirm(options));
        }}
      >
        ask
      </button>
      {confirmDialog}
    </>
  );
}

describe("useConfirm (P2-01)", () => {
  it("renders nothing until asked", () => {
    render(<Harness options={{}} onResult={noop} />);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("shows the title and description supplied", async () => {
    render(
      <Harness
        options={{ title: "Delete file?", description: "Cannot be undone." }}
        onResult={noop}
      />,
    );
    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() =>
      expect(screen.getByText("Delete file?")).toBeInTheDocument(),
    );
    expect(screen.getByText("Cannot be undone.")).toBeInTheDocument();
  });

  it("resolves true when confirmed", async () => {
    let result;
    render(
      <Harness options={{ okText: "Yes" }} onResult={(r) => (result = r)} />,
    );
    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() => screen.getByRole("button", { name: "Yes" }));
    screen.getByRole("button", { name: "Yes" }).click();
    await waitFor(() => expect(result).toBe(true));
  });

  it("resolves false when cancelled — the promise must never dangle", async () => {
    let result;
    render(
      <Harness options={{ cancelText: "No" }} onResult={(r) => (result = r)} />,
    );
    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() => screen.getByRole("button", { name: "No" }));
    screen.getByRole("button", { name: "No" }).click();
    await waitFor(() => expect(result).toBe(false));
  });

  it("closes the dialog after settling", async () => {
    render(<Harness options={{ okText: "Go" }} onResult={noop} />);
    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() => screen.getByRole("button", { name: "Go" }));
    screen.getByRole("button", { name: "Go" }).click();
    await waitFor(() =>
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument(),
    );
  });

  it("can be asked twice in a row", async () => {
    const seen = [];
    render(
      <Harness options={{ okText: "Yes" }} onResult={(r) => seen.push(r)} />,
    );
    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() => screen.getByRole("button", { name: "Yes" }));
    screen.getByRole("button", { name: "Yes" }).click();
    await waitFor(() => expect(seen).toHaveLength(1));

    screen.getByRole("button", { name: "ask" }).click();
    await waitFor(() => screen.getByRole("button", { name: "Yes" }));
    screen.getByRole("button", { name: "Yes" }).click();
    await waitFor(() => expect(seen).toEqual([true, true]));
  });
});
