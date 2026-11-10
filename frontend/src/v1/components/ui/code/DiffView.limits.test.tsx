import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { DiffView } from "./DiffView";

// Stands in for a diff that hit jsdiff's time limit, which no fixture can hit
// deterministically.
vi.mock("@v1/lib/code/diff", async (original) => ({
  ...(await original<typeof import("@v1/lib/code/diff")>()),
  computeLineDiff: () => null,
}));

it("says two texts are too large to compare instead of rendering a diff", async () => {
  const { container } = renderV1(<DiffView oldText="a" newText="b" />);
  expect(screen.getByRole("status").textContent).toContain(
    "Too large to compare",
  );
  expect(screen.queryByRole("region", { name: "Changes" })).toBeNull();
  expect(container.querySelector("[data-slot=diff-summary]")).toBeNull();
  await expect(container).toHaveNoA11yViolations();
});
