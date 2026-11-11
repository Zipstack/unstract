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
