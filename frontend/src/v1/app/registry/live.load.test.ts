import { afterEach, expect, it, vi } from "vitest";

/*
 * load() runs once, when live.ts is imported, so each case imports it afresh.
 * Kept apart from live.test.ts, which mocks ./entries for every test there.
 */
async function importLive() {
  vi.resetModules();
  return import("./live");
}

afterEach(() => {
  vi.doUnmock("./entries");
});

it("falls back to OSS, with a console error, on an unknown distribution", async () => {
  vi.stubEnv("VITE_DISTRIBUTION", "saas");
  vi.stubEnv("VITE_V1_DEV_ROUTES", "true");
  const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const { LIVE_REGISTRY } = await importLive();
  expect(error).toHaveBeenCalledWith(
    "VITE_DISTRIBUTION=saas is not one of oss, cloud, onprem; using oss",
  );
  // v0 imports this module eagerly, so it must load rather than throw, and
  // as OSS: the demo pages ship in every distribution, so both stay live.
  expect(LIVE_REGISTRY.entries.map((e) => e.page)).toEqual([
    "DEMO-PAGE",
    "DEMO-REVIEW",
  ]);
});

it("fails loudly in development when the registry is invalid", async () => {
  expect(import.meta.env.DEV).toBe(true);
  vi.doMock("./entries", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./entries")>()),
    PAGES: [
      {
        page: "UN05",
        v1Routes: [],
        replaces: [],
        toV0: {},
        toV1: {},
        toggle: false,
        distributions: ["oss"],
        registeredBy: "P3-T01",
      },
    ],
  }));
  await expect(importLive()).rejects.toThrow(
    "Invalid v1 route registry:\nUN05: has no v1 routes",
  );
});
