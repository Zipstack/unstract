import { describe, expect, it } from "vitest";
import { DEMO_PAGES, PAGES } from "./entries";
import {
  activeEntries,
  fillPattern,
  resolvePageUrl,
  resolveRoute,
} from "./resolve";
import type { RegistryEntry } from "./types";
import { registryProblems } from "./validate";

const plain: RegistryEntry = {
  page: "UN05",
  v1Routes: ["/:orgName/workflows", "/:orgName/flows/:id/*"],
  replaces: ["/:orgName/workflows", "/:orgName/workflows/:id"],
  toV0: {
    "/:orgName/workflows": "/:orgName/workflows",
    "/:orgName/flows/:id/*": "/:orgName/workflows/:id",
  },
  toV1: {
    "/:orgName/workflows": "/:orgName/workflows",
    "/:orgName/workflows/:id": "/:orgName/flows/:id/*",
  },
  toggle: false,
  distributions: ["oss", "cloud"],
  registeredBy: "P3-T01",
};

const review: RegistryEntry = {
  page: "UN11",
  v1Routes: ["/:orgName/hitl", "/:orgName/hitl/:id/approve"],
  replaces: ["/:orgName/review", "/:orgName/review/approve"],
  toV0: {
    "/:orgName/hitl": "/:orgName/review",
    "/:orgName/hitl/:id/approve": "/:orgName/review/approve",
  },
  toV1: {
    "/:orgName/review": "/:orgName/hitl",
    "/:orgName/review/approve": "/:orgName/hitl",
  },
  toggle: true,
  distributions: ["cloud"],
  registeredBy: "P6-T07",
};

const entries = [plain, review];

it("the fixtures are valid registry entries", () => {
  expect(registryProblems(entries)).toEqual([]);
});
const at = (pathname: string, oldVersion: boolean | null = false) =>
  resolveRoute({ pathname }, { entries, oldVersion });

describe("resolveRoute", () => {
  it("renders v0 for an unregistered URL, and everywhere with an empty registry", () => {
    expect(at("/acme/logs")).toEqual({ kind: "v0" });
    for (const path of ["/acme/workflows", "/acme/review", "/acme/hitl"]) {
      expect(
        resolveRoute({ pathname: path }, { entries: [], oldVersion: true }),
      ).toEqual({
        kind: "v0",
      });
    }
  });

  it("renders v1 for a registered page's v1 route, whatever the preference", () => {
    for (const pref of [true, false, null]) {
      expect(at("/acme/flows/7/runs", pref)).toEqual({
        kind: "v1",
        entry: plain,
      });
      // A route that is both v0 and v1 renders v1 without redirecting.
      expect(at("/acme/workflows", pref)).toEqual({ kind: "v1", entry: plain });
    }
  });

  it("redirects a registered page's v0 URL to its v1 route, keeping query and hash", () => {
    expect(
      resolveRoute(
        { pathname: "/acme/workflows/7", search: "?q=1", hash: "#x" },
        { entries, oldVersion: false },
      ),
    ).toEqual({ kind: "redirect", to: "/acme/flows/7?q=1#x" });
  });

  it("keeps encoded params inside their segment when redirecting", () => {
    expect(at("/a%2Fb/workflows/x%3Fy%23z")).toEqual({
      kind: "redirect",
      to: "/a%2Fb/flows/x%3Fy%23z",
    });
  });

  it("toggle page, new version: v1 renders and v0 URLs redirect", () => {
    expect(at("/acme/hitl", false)).toEqual({ kind: "v1", entry: review });
    expect(at("/acme/review/approve", false)).toEqual({
      kind: "redirect",
      to: "/acme/hitl",
    });
  });

  it("toggle page, old version: v0 renders and v1 URLs redirect to the mapped v0 route", () => {
    expect(at("/acme/review", true)).toEqual({ kind: "v0" });
    expect(at("/acme/hitl/9/approve", true)).toEqual({
      kind: "redirect",
      to: "/acme/review/approve",
    });
  });

  it("toggle page, user unknown: v0 URLs stay on v0 and v1 URLs on v1", () => {
    expect(at("/acme/review", null)).toEqual({ kind: "v0" });
    expect(at("/acme/hitl", null)).toEqual({ kind: "v1", entry: review });
  });

  it("the preference changes nothing on a page without the toggle", () => {
    expect(at("/acme/workflows/7", true)).toEqual(
      at("/acme/workflows/7", false),
    );
  });

  it("defensively, the most specific pattern wins if two pages overlap", () => {
    const logs: RegistryEntry = {
      ...plain,
      page: "UN10",
      v1Routes: ["/:orgName/flows/:id/logs"],
      replaces: [],
      toV0: {},
      toV1: {},
    };
    // A valid registry has no such overlap; validation rejects it.
    expect(registryProblems([plain, logs])).toContain(
      "UN05 /:orgName/flows/:id/* overlaps UN10 /:orgName/flows/:id/logs",
    );
    const both = { entries: [plain, logs], oldVersion: false };
    expect(resolveRoute({ pathname: "/acme/flows/7/logs" }, both)).toEqual({
      kind: "v1",
      entry: logs,
    });
    expect(resolveRoute({ pathname: "/acme/flows/7/runs" }, both)).toEqual({
      kind: "v1",
      entry: plain,
    });
  });
});

describe("activeEntries", () => {
  it("keeps registered pages shipped in the distribution only", () => {
    const live = new Set(["UN05", "UN11"] as const);
    expect(activeEntries(entries, live, "oss")).toEqual([plain]);
    expect(activeEntries(entries, live, "cloud")).toEqual([plain, review]);
    expect(activeEntries(entries, live, "onprem")).toEqual([]);
    expect(activeEntries(entries, new Set(["UN11"] as const), "cloud")).toEqual(
      [review],
    );
  });
});

describe("resolvePageUrl", () => {
  const params = { orgName: "acme", id: "9" };
  it("gives the v1 URL for a live page", () => {
    expect(
      resolvePageUrl("UN11", "/:orgName/hitl/:id/approve", params, entries, {
        entries,
        oldVersion: false,
      }),
    ).toBe("/acme/hitl/9/approve");
  });
  it("gives the mapped v0 URL in old-version mode or when the page is not live", () => {
    for (const ctx of [
      { entries, oldVersion: true },
      { entries: [], oldVersion: false },
    ]) {
      expect(
        resolvePageUrl(
          "UN11",
          "/:orgName/hitl/:id/approve",
          params,
          entries,
          ctx,
        ),
      ).toBe("/acme/review/approve");
    }
  });
  it("ignores the old-version choice on a page without the toggle", () => {
    expect(
      resolvePageUrl("UN05", "/:orgName/flows/:id/*", params, entries, {
        entries,
        oldVersion: true,
      }),
    ).toBe("/acme/flows/9");
  });
  it("gives a declared, not-live page's v0 URL", () => {
    expect(
      resolvePageUrl("UN05", "/:orgName/flows/:id/*", params, entries, {
        entries: [],
        oldVersion: false,
      }),
    ).toBe("/acme/workflows/9");
  });
  it("decides liveness by page key, not object identity", () => {
    expect(
      resolvePageUrl("UN11", "/:orgName/hitl", params, entries, {
        entries: [{ ...review }],
        oldVersion: false,
      }),
    ).toBe("/acme/hitl");
  });
  it("encodes raw param values", () => {
    expect(
      resolvePageUrl(
        "UN11",
        "/:orgName/hitl/:id/approve",
        { orgName: "a/b", id: "c?d" },
        entries,
        {
          entries,
          oldVersion: false,
        },
      ),
    ).toBe("/a%2Fb/hitl/c%3Fd/approve");
  });
  it("is null for an undeclared page or an unknown pattern", () => {
    const ctx = { entries: [], oldVersion: false };
    expect(
      resolvePageUrl("UN09", "/:orgName/hitl", params, entries, ctx),
    ).toBeNull();
    expect(
      resolvePageUrl("UN11", "/:orgName/nope", params, entries, ctx),
    ).toBeNull();
  });
  it("is null, not a throw or a wrong URL, when a param is missing or empty", () => {
    const missingOrEmpty: Record<string, string>[] = [
      { orgName: "acme" },
      { orgName: "", id: "9" },
    ];
    for (const ctx of [
      { entries, oldVersion: false },
      { entries: [], oldVersion: false },
    ]) {
      for (const bad of missingOrEmpty) {
        expect(
          resolvePageUrl(
            "UN11",
            "/:orgName/hitl/:id/approve",
            bad,
            entries,
            ctx,
          ),
        ).toBeNull();
      }
    }
  });
  it("lets a final splat be omitted", () => {
    expect(
      resolvePageUrl("UN05", "/:orgName/flows/:id/*", params, entries, {
        entries,
        oldVersion: false,
      }),
    ).toBe("/acme/flows/9");
  });
});

/** Mapping both ways, for every entry the app declares. */
describe.each([...PAGES, ...DEMO_PAGES])("$page mapping", (entry) => {
  const self = { entries: [entry] };
  // Placeholder params; a splat is left empty, as generatePath drops it.
  const fill = (pattern: string) =>
    fillPattern(pattern, {
      ...Object.fromEntries(
        [...pattern.matchAll(/:(\w+)/g)].map(([, name]) => [name, `p-${name}`]),
      ),
      "*": "",
    });

  it("each v0 route redirects to its mapped v1 route, which renders v1", () => {
    for (const [v0, v1] of Object.entries(entry.toV1)) {
      const r = resolveRoute(
        { pathname: fill(v0) },
        { ...self, oldVersion: false },
      );
      if (v0 === v1) {
        expect(r).toEqual({ kind: "v1", entry });
      } else {
        expect(r).toEqual({ kind: "redirect", to: fill(v1) });
        expect(
          resolveRoute({ pathname: fill(v1) }, { ...self, oldVersion: false }),
        ).toEqual({ kind: "v1", entry });
      }
    }
  });

  it.runIf(entry.toggle)(
    "in old-version mode each v1 route redirects to its mapped v0 route, which renders v0",
    () => {
      for (const [v1, v0] of Object.entries(entry.toV0)) {
        const r = resolveRoute(
          { pathname: fill(v1) },
          { ...self, oldVersion: true },
        );
        expect(r).toEqual(
          v1 === v0 ? { kind: "v0" } : { kind: "redirect", to: fill(v0) },
        );
        expect(
          resolveRoute({ pathname: fill(v0) }, { ...self, oldVersion: true }),
        ).toEqual({
          kind: "v0",
        });
      }
    },
  );
});
