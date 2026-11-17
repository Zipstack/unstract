import { clearBrowserStorage } from "@v1";
import { afterEach, describe, expect, it } from "vitest";

import { evictExpiredCache, getCached, setCache } from "./metricsCache.js";

describe("metricsCache", () => {
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("keeps entries in sessionStorage, never localStorage", () => {
    setCache("overview", { org: "org_1" }, { total: 3 });

    expect(getCached("overview", { org: "org_1" })).toEqual({ total: 3 });
    expect(Object.keys(window.sessionStorage)).toHaveLength(1);
    expect(window.localStorage.length).toBe(0);
  });

  // A dashboard reply that resolves after logout (e.g. in another tab) must
  // not leave the organization's data in storage that outlives the tab.
  it("a reply landing after logout does not reach localStorage", () => {
    clearBrowserStorage();

    setCache("summary", { org: "org_1" }, { executions: 42 });

    expect(window.localStorage.length).toBe(0);
  });

  it("evicts expired entries from sessionStorage and keeps live ones", () => {
    const now = Date.now();
    window.sessionStorage.setItem(
      "dashboard_metrics_overview_old",
      JSON.stringify({ data: {}, expiry: now - 1 }),
    );
    window.sessionStorage.setItem("dashboard_metrics_overview_bad", "{");
    window.sessionStorage.setItem(
      "dashboard_metrics_overview_live",
      JSON.stringify({ data: {}, expiry: now + 60_000 }),
    );

    evictExpiredCache();

    expect(Object.keys(window.sessionStorage)).toEqual([
      "dashboard_metrics_overview_live",
    ]);
  });
});
