import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildRegistry } from "./registry";
import { makeSlot } from "./Slot";
import type { PluginManifest } from "./types";

const fallback = <span>fallback</span>;

function slotFor(manifests: PluginManifest[]) {
  const report = vi.fn();
  const Slot = makeSlot(buildRegistry(manifests, "cloud"), report);
  return { Slot, report };
}

describe("Slot", () => {
  beforeEach(() => {
    // React logs caught render errors; the report spy is the assertion.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the fallback silently when no plugin fills it", () => {
    const { Slot, report } = slotFor([]);
    render(<Slot id="shell.product-switcher" props={{}} fallback={fallback} />);
    expect(screen.getByText("fallback")).toBeInTheDocument();
    expect(report).not.toHaveBeenCalled();
  });

  it("renders the filler when a plugin fills it", async () => {
    const { Slot, report } = slotFor([
      {
        id: "switcher",
        distributions: ["cloud"],
        slots: {
          "shell.product-switcher": async () => ({
            default: () => <span>switcher</span>,
          }),
        },
      },
    ]);
    render(<Slot id="shell.product-switcher" props={{}} fallback={fallback} />);
    expect(await screen.findByText("switcher")).toBeInTheDocument();
    expect(report).not.toHaveBeenCalled();
  });

  it("reports a filler that fails to load and shows the fallback", async () => {
    const { Slot, report } = slotFor([
      {
        id: "broken",
        distributions: ["cloud"],
        slots: {
          "shell.product-switcher": () => Promise.reject(new Error("chunk")),
        },
      },
    ]);
    render(<Slot id="shell.product-switcher" props={{}} fallback={fallback} />);
    expect(await screen.findByText("fallback")).toBeInTheDocument();
    await vi.waitFor(() =>
      expect(report).toHaveBeenCalledWith(
        "broken",
        "shell.product-switcher",
        expect.objectContaining({ message: "chunk" }),
      ),
    );
  });

  it("keeps a failing plugin from taking down another slot", async () => {
    const { Slot, report } = slotFor([
      {
        id: "broken",
        distributions: ["cloud"],
        slots: {
          "account-menu.plan-billing": async () => ({
            default: () => {
              throw new Error("render");
            },
          }),
        },
      },
      {
        id: "switcher",
        distributions: ["cloud"],
        slots: {
          "shell.product-switcher": async () => ({
            default: () => <span>switcher</span>,
          }),
        },
      },
    ]);
    render(
      <>
        <Slot id="account-menu.plan-billing" props={{}} fallback={fallback} />
        <Slot id="shell.product-switcher" props={{}} fallback={null} />
      </>,
    );
    expect(await screen.findByText("switcher")).toBeInTheDocument();
    expect(await screen.findByText("fallback")).toBeInTheDocument();
    expect(report).toHaveBeenCalledTimes(1);
    expect(report).toHaveBeenCalledWith(
      "broken",
      "account-menu.plan-billing",
      expect.objectContaining({ message: "render" }),
    );
  });
});
