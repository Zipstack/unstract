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
    expect(() => buildRegistry([billing], "cloud", ["/billing"])).toThrow(
      /\/billing.*OSS.*billing/,
    );
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
});
