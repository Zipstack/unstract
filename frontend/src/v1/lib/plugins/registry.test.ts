import { describe, expect, it } from "vitest";
import { buildRegistry, PluginConflictError } from "./registry";
import type { PluginManifest } from "./types";

const load = () => Promise.resolve({ default: () => null });

const billing: PluginManifest = {
  id: "billing",
  distributions: ["cloud"],
  slots: { "account-menu.plan-billing": load },
  routes: [{ path: "/billing", load }],
};
const switcher: PluginManifest = {
  id: "switcher",
  distributions: ["cloud", "onprem"],
  slots: { "shell.product-switcher": load },
};

describe("buildRegistry", () => {
  it("keeps only plugins that list the current distribution", () => {
    const onprem = buildRegistry([billing, switcher], "onprem");
    expect(onprem.plugins).toEqual(["switcher"]);
    expect(onprem.slot("account-menu.plan-billing")).toBeUndefined();
    expect(onprem.slot("shell.product-switcher")?.owner).toBe("switcher");
    expect(onprem.routes).toEqual([]);

    const cloud = buildRegistry([billing, switcher], "cloud");
    expect(cloud.plugins).toEqual(["billing", "switcher"]);
    expect(cloud.routes.map((r) => r.path)).toEqual(["/billing"]);
  });

  it("offers nothing in the OSS build", () => {
    const oss = buildRegistry([billing, switcher], "oss");
    expect(oss.plugins).toEqual([]);
    expect(oss.slot("shell.product-switcher")).toBeUndefined();
  });

  it("fails on a slot filled twice, naming both plugins", () => {
    const twin = { ...switcher, id: "twin" };
    expect(() => buildRegistry([switcher, twin], "cloud")).toThrow(
      PluginConflictError,
    );
    expect(() => buildRegistry([switcher, twin], "cloud")).toThrow(
      /shell\.product-switcher.*switcher.*twin/,
    );
  });

  it("fails on a route two plugins contribute, naming both", () => {
    const other: PluginManifest = {
      id: "other",
      distributions: ["cloud"],
      routes: [{ path: "/billing", load }],
    };
    expect(() => buildRegistry([billing, other], "cloud")).toThrow(
      /\/billing.*billing.*other/,
    );
  });

  it("fails on a route OSS also defines, naming both owners", () => {
    expect(() =>
      buildRegistry([billing], "cloud", { ossRoutes: ["/billing"] }),
    ).toThrow(/\/billing.*OSS.*billing/);
  });

  it("fails on overlapping routes when given an overlap rule, naming both paths", () => {
    // Stands in for patternsOverlap: every /billing route overlaps.
    const prefix = (a: string, b: string) =>
      a.startsWith("/billing") && b.startsWith("/billing");
    const other = {
      ...billing,
      id: "other",
      slots: {},
      routes: [{ path: "/billing/*", load }],
    };
    expect(() =>
      buildRegistry([billing, other], "cloud", { overlaps: prefix }),
    ).toThrow(/\/billing\/\* \(overlaps \/billing\).*billing.*other/);
    expect(() => buildRegistry([billing, other], "cloud")).not.toThrow();
  });

  it("checks conflicts in every distribution, not only the current one", () => {
    const twin = { ...billing, id: "twin", routes: [] };
    expect(() => buildRegistry([billing, twin], "oss")).toThrow(
      /account-menu\.plan-billing/,
    );
  });

  it("lets plugins in disjoint distributions fill the same slot", () => {
    const cloudOnly = { ...switcher, distributions: ["cloud"] as const };
    const onpremOnly = {
      ...switcher,
      id: "switcher-onprem",
      distributions: ["onprem"] as const,
    };
    const onprem = buildRegistry([cloudOnly, onpremOnly], "onprem");
    expect(onprem.slot("shell.product-switcher")?.owner).toBe(
      "switcher-onprem",
    );
  });

  it("fails on a plugin that declares no distribution", () => {
    const undeclared = { ...switcher, distributions: [] };
    expect(() => buildRegistry([undeclared], "cloud")).toThrow(
      /switcher declares no distributions/,
    );
  });

  it("fails on two plugins with the same id", () => {
    expect(() => buildRegistry([switcher, switcher], "cloud")).toThrow(
      /plugin id switcher is used twice/,
    );
  });

  it("fails on a slot id no plugin contract defines, naming the plugin", () => {
    const typo = {
      id: "typo",
      distributions: ["cloud"],
      slots: { "shell.product-swicher": load },
    } as unknown as PluginManifest;
    expect(() => buildRegistry([typo], "cloud")).toThrow(PluginConflictError);
    expect(() => buildRegistry([typo], "cloud")).toThrow(
      /typo.*shell\.product-swicher/,
    );
  });

  it("fails on a distribution no build offers, naming the plugin", () => {
    const stray = {
      id: "stray",
      distributions: ["cloud", "onprm"],
    } as unknown as PluginManifest;
    expect(() => buildRegistry([stray], "cloud")).toThrow(PluginConflictError);
    expect(() => buildRegistry([stray], "cloud")).toThrow(/stray.*onprm/);
  });

  it.each([
    ["an undefined slot", { slots: { "shell.product-switcher": undefined } }],
    ["a string slot", { slots: { "shell.product-switcher": "./X" } }],
  ])("fails on %s, naming the plugin and the slot", (_, extra) => {
    const bad = {
      id: "bad",
      distributions: ["cloud"],
      ...extra,
    } as unknown as PluginManifest;
    expect(() => buildRegistry([bad], "cloud")).toThrow(PluginConflictError);
    expect(() => buildRegistry([bad], "cloud")).toThrow(
      /bad fills slot shell\.product-switcher with (undefined|string), not a loader function/,
    );
  });

  it("fails on a route whose load is not a function, naming the plugin and the path", () => {
    const bad = {
      id: "bad",
      distributions: ["cloud"],
      routes: [{ path: "/bad", load: "./Bad" }],
    } as unknown as PluginManifest;
    expect(() => buildRegistry([bad], "cloud")).toThrow(
      /bad route \/bad has no load function/,
    );
  });

  it.each([
    [{ load }],
    [{ path: 42, load }],
  ])("fails on a route without a string path, naming the plugin (%o)", (route) => {
    const bad = {
      id: "bad",
      distributions: ["cloud"],
      routes: [route],
    } as unknown as PluginManifest;
    expect(() => buildRegistry([bad], "cloud")).toThrow(
      /bad route 0 has no string path/,
    );
  });

  it("checks route paths with the given pattern rule, naming the plugin", () => {
    const optional = {
      ...billing,
      routes: [{ path: "/billing/:id?", load }],
    };
    const noOptional = (p: string) =>
      p.includes("?") ? "optional segments are not accepted" : null;
    expect(() =>
      buildRegistry([optional], "cloud", { patternProblem: noOptional }),
    ).toThrow(
      /billing route \/billing\/:id\? is not accepted: optional segments/,
    );
    expect(() => buildRegistry([optional], "cloud")).not.toThrow();
  });

  it("rejects a relative route path by default", () => {
    const relative = { ...billing, routes: [{ path: "billing", load }] };
    expect(() => buildRegistry([relative], "cloud")).toThrow(
      /billing route billing is not accepted: must start with \//,
    );
  });
});
