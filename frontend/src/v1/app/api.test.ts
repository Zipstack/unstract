import {
  LAST_USER_STORAGE_KEY,
  OLD_VERSION_ON,
  oldVersionStorageKey,
} from "@v1/lib/oldVersion";
import { beforeEach, describe, expect, it, vi } from "vitest";

// A declared page that is not live yet, beside the real demo pages.
vi.mock("@v1/app/registry/entries", async (importOriginal) => {
  const real =
    await importOriginal<typeof import("@v1/app/registry/entries")>();
  return {
    ...real,
    PAGES: [
      {
        page: "UN05",
        v1Routes: ["/:orgName/flows/:id"],
        replaces: ["/:orgName/workflows/:id"],
        toV0: { "/:orgName/flows/:id": "/:orgName/workflows/:id" },
        toV1: { "/:orgName/workflows/:id": "/:orgName/flows/:id" },
        toggle: false,
        distributions: ["oss", "cloud", "onprem"],
        registeredBy: "P3-T01",
      },
    ],
    REGISTERED_PAGES: [],
  };
});

/**
 * The public entry with the demo pages live, as in the E2E image. The
 * registry and the preference store are read when their modules load, so
 * each test imports them afresh after seeding storage.
 */
async function loadApi() {
  vi.stubEnv("VITE_V1_DEV_ROUTES", "true");
  vi.resetModules();
  const api = await import("@v1/app/api");
  const { useOldVersionStore } = await import("@v1/stores/oldVersion");
  return { ...api, useOldVersionStore };
}

const REVIEW = "/:orgName/v1-demo-review";
const acme = { orgName: "acme" };

beforeEach(() => {
  window.localStorage.clear();
});

describe("resolveUrl", () => {
  it("follows the signed-in user's old-version choice on a toggle page", async () => {
    const { resolveUrl, setOldVersion, useOldVersionStore } = await loadApi();
    useOldVersionStore.getState().setUser("7");
    expect(resolveUrl("DEMO-REVIEW", REVIEW, acme)).toBe(
      "/acme/v1-demo-review",
    );

    expect(setOldVersion(true)).toBe(true);
    expect(resolveUrl("DEMO-REVIEW", REVIEW, acme)).toBe(
      "/acme/v0-demo-review",
    );
  });

  it("before the session loads, uses the last user known to this browser", async () => {
    window.localStorage.setItem(LAST_USER_STORAGE_KEY, "7");
    window.localStorage.setItem(oldVersionStorageKey("7"), OLD_VERSION_ON);
    const { resolveUrl } = await loadApi();
    expect(resolveUrl("DEMO-REVIEW", REVIEW, acme)).toBe(
      "/acme/v0-demo-review",
    );
  });

  it("links a declared page that is not live yet to its v0 URL", async () => {
    const { resolveUrl } = await loadApi();
    expect(
      resolveUrl("UN05", "/:orgName/flows/:id", { orgName: "acme", id: "9" }),
    ).toBe("/acme/workflows/9");
  });

  it("is null for a page this build does not declare", async () => {
    const { resolveUrl } = await loadApi();
    expect(resolveUrl("UN11", "/:orgName/hitl", acme)).toBeNull();
  });
});
