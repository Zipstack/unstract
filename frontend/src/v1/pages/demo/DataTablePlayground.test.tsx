// TEMP (UN-4346): for dev testing only. Removed before merging; never merge this.
import { screen, within } from "@testing-library/react";
import { toast } from "@v1/lib/notify";
import { renderV1 } from "@v1/test";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DataTablePlayground } from "./DataTablePlayground";
import { fakeGet, fakeServer } from "./fakeDeployments";

const initial = { ...fakeServer };
beforeEach(() => {
  Object.assign(fakeServer, { ...initial, latencyMs: 0 });
});
afterEach(() => {
  Object.assign(fakeServer, initial);
});

const rows = () =>
  document.querySelectorAll("[data-slot=data-table-row]").length;

it("pages, sorts and searches on the dummy server", async () => {
  const first = await fakeGet("/x/?page=1&page_size=25");
  expect(first.count).toBe(1000);
  expect(first.results).toHaveLength(25);
  const last = await fakeGet("/x/?page=40&page_size=25&ordering=-total_runs");
  expect(last.results).toHaveLength(25);
  expect(last.results[0].total_runs).toBeGreaterThanOrEqual(
    last.results[24].total_runs,
  );
  const found = await fakeGet("/x/?search=kyc&page_size=500");
  expect(found.count).toBeGreaterThan(0);
  expect(found.results.every((r) => r.name.startsWith("kyc"))).toBe(true);
});

it("loads a page, shows a forced error with Retry, and toasts bulk results", async () => {
  const success = vi.spyOn(toast, "success");
  const failure = vi.spyOn(toast, "error");
  const { user } = renderV1(<DataTablePlayground />);
  await screen.findByText("Showing 1 to 25 of 1000 entries");
  expect(rows()).toBe(25);

  await user.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText("Showing 26 to 50 of 1000 entries");

  await user.click(screen.getByRole("radio", { name: "The list (GET)" }));
  await user.click(screen.getByRole("button", { name: "Refetch" }));
  await screen.findByText("Could not load deployments");
  await user.click(screen.getByRole("radio", { name: "Nothing" }));
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Showing 26 to 50 of 1000 entries");

  await user.click(
    screen.getByRole("checkbox", { name: "Select all rows on this page" }),
  );
  const bar = screen.getByRole("region", {
    name: "Bulk actions for Dummy API deployments",
  });
  await user.click(
    within(bar).getByRole("button", { name: "Restart selected" }),
  );
  await vi.waitFor(() => expect(success).toHaveBeenCalled());

  await user.click(screen.getByRole("radio", { name: "Bulk actions (POST)" }));
  await user.click(
    screen.getByRole("checkbox", { name: "Select all rows on this page" }),
  );
  await user.click(
    within(
      screen.getByRole("region", {
        name: "Bulk actions for Dummy API deployments",
      }),
    ).getByRole("button", { name: "Delete selected" }),
  );
  await vi.waitFor(() => expect(failure).toHaveBeenCalled());
});
