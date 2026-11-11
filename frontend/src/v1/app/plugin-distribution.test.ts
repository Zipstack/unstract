import { expect, it, vi } from "vitest";

// The frontend image passes VITE_DISTRIBUTION through even when unset, as "".
it.each([
  "",
  " OSS ",
  "cloud",
])("VITE_DISTRIBUTION=%j loads the plugin registry", async (value) => {
  vi.stubEnv("VITE_DISTRIBUTION", value);
  vi.resetModules();
  await expect(import("@v1/plugins")).resolves.toHaveProperty("registry");
});

it("rejects a distribution it does not know", async () => {
  vi.stubEnv("VITE_DISTRIBUTION", "cluod");
  vi.resetModules();
  await expect(import("@v1/plugins")).rejects.toThrow(/must be one of/);
});

it("rejects a plugin route on a page the OSS route registry declares", async () => {
  vi.resetModules();
  const { pluginRegistry } = await import("@v1/plugins");
  expect(() =>
    pluginRegistry(
      [
        {
          id: "clash",
          distributions: ["cloud"],
          routes: [
            {
              path: "/:orgName/v1-demo",
              load: async () => ({ default: () => null }),
            },
          ],
        },
      ],
      "cloud",
    ),
  ).toThrow(/\/:orgName\/v1-demo.*\bOSS\b.*\bclash\b/);
});

it("logs a plugin failure and raises one error notification per slot", async () => {
  vi.resetModules();
  const { reportPluginError } = await import("@v1/plugins");
  const { setNotifier } = await import("@v1/lib/notify");
  const shown: unknown[] = [];
  const unregister = setNotifier({
    show: (input) => {
      shown.push(input);
      return input.id ?? "";
    },
    dismiss: () => undefined,
  });
  const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const error = new Error("chunk");
  reportPluginError("billing", "account-menu.plan-billing", error);
  unregister();
  expect(logged).toHaveBeenCalledWith(
    "v1 plugin billing failed in slot account-menu.plan-billing",
    error,
  );
  expect(shown).toEqual([
    expect.objectContaining({
      kind: "error",
      id: "plugin-billing-account-menu.plan-billing",
    }),
  ]);
});
