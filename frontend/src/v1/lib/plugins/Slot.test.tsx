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

  it("loads again on a later mount after a failed load", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error("chunk"))
      .mockResolvedValue({ default: () => <span>switcher</span> });
    const { Slot, report } = slotFor([
      {
        id: "flaky",
        distributions: ["cloud"],
        slots: { "shell.product-switcher": load },
      },
    ]);
    const first = render(
      <Slot id="shell.product-switcher" props={{}} fallback={fallback} />,
    );
    await vi.waitFor(() => expect(report).toHaveBeenCalledTimes(1));
    first.unmount();
    render(<Slot id="shell.product-switcher" props={{}} fallback={fallback} />);
    expect(await screen.findByText("switcher")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("recovers in place on the next render after a failed load", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error("chunk"))
      .mockResolvedValue({ default: () => <span>switcher</span> });
    const { Slot, report } = slotFor([
      {
        id: "flaky",
        distributions: ["cloud"],
        slots: { "shell.product-switcher": load },
      },
    ]);
    // A fresh element each time, in the same position: React re-renders the
    // mounted slot and its boundary instead of mounting new ones.
    const tree = () => (
      <Slot id="shell.product-switcher" props={{}} fallback={fallback} />
    );
    const { rerender } = render(tree());
    await vi.waitFor(() => expect(report).toHaveBeenCalledTimes(1));
    rerender(tree());
    expect(await screen.findByText("switcher")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
