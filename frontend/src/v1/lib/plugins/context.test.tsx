import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { buildRegistry, makeSlot, PluginProvider, Slot } from "./index";

const fallback = <span>fallback</span>;

it("a slot with no provider shows its fallback", () => {
  render(<Slot id="shell.product-switcher" props={{}} fallback={fallback} />);
  expect(screen.getByText("fallback")).toBeInTheDocument();
});

it("a slot renders the provider's filler", async () => {
  const registry = buildRegistry(
    [
      {
        id: "switcher",
        distributions: ["cloud"],
        slots: {
          "shell.product-switcher": async () => ({
            default: () => <span>switcher</span>,
          }),
        },
      },
    ],
    "cloud",
  );
  render(
    <PluginProvider slot={makeSlot(registry, () => undefined)}>
      <Slot id="shell.product-switcher" props={{}} fallback={fallback} />
    </PluginProvider>,
  );
  expect(await screen.findByText("switcher")).toBeInTheDocument();
});
