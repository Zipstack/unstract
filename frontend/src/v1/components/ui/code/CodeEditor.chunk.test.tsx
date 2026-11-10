import { screen } from "@testing-library/react";
import { renderV1 } from "@v1/test";
import { expect, it, vi } from "vitest";
import { CodeEditor } from "./CodeEditor";

// The lazy chunk itself fails to load (a stale hash after a deploy, a network
// error): the editor shows its own error instead of unmounting the page.
// Never the real loader, which would inject the CDN script.
vi.mock("@monaco-editor/loader", () => ({
  default: { init: () => new Promise(() => undefined) },
}));
vi.mock("@monaco-editor/react", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

it("shows its own error when the editor chunk fails to load", async () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  renderV1(
    <div>
      <p>Rest of the page</p>
      <CodeEditor aria-label="Broken" />
    </div>,
  );
  expect((await screen.findByRole("alert")).textContent).toContain(
    "The editor could not load",
  );
  expect(screen.getByText("Rest of the page")).toBeTruthy();
  // One alert, though both the boundary and the loader watch see the failure.
  expect(screen.getAllByRole("alert")).toHaveLength(1);
});
