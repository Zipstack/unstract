/*
 * `RequireGuest` deciding where a visitor goes, across the three shapes the
 * product plugin can take in this repository.
 *
 * The plugin is overlay-only: `frontend/src/plugins/` does not exist here, so
 * every shape has to be stubbed. An earlier version of this file stubbed it as
 * an EMPTY module, which looked like "no plugin" but was worse than that — the
 * first statement of the function under test threw, control jumped to the
 * `catch`, and the fallback these tests exist for was never reached. All three
 * passed with the production change deleted (review on #2494, 2026-11).
 *
 * So the stub is now functional, and the shapes are separated:
 *
 *   PRESENT   — a working plugin. Exercises the fallback for real.
 *   PARTIAL   — `externalHomeForProduct` missing, which is what a deployment
 *               looks like between this PR merging and unstract-cloud#1998.
 *   ABSENT    — no plugin at all, i.e. an OSS-only build.
 *
 * `/flow` rather than an absolute URL on purpose: that is the shape
 * `config.flowUrl` actually has in every deployment.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const PLUGIN = "../../../plugins/store/select-product-store.js";
const SESSION = "../../../store/session-store";

/** A plugin that can answer both questions. */
const PRESENT = {
  externalHomeForSelectedProduct: () => null,
  externalHomeForProduct: (p) => (p === "flow" ? "/flow" : null),
};
/** The store already knows, so the query must not be consulted. */
const PRESENT_WITH_STORED = {
  externalHomeForSelectedProduct: () => "/flow",
  externalHomeForProduct: () => "/should-not-be-used",
};
/** unstract-cloud#1998 not yet merged: the by-name accessor does not exist. */
const PARTIAL = { externalHomeForSelectedProduct: () => null };

let assigned;
const stubLocation = () => {
  assigned = [];
  Object.defineProperty(window, "location", {
    value: {
      assign: (u) => assigned.push(u),
      href: "https://host/landing",
      pathname: "/landing",
      search: "",
      origin: "https://host",
    },
    writable: true,
    configurable: true,
  });
};

const mount = async ({ plugin, loggedIn = true, url }) => {
  vi.resetModules();
  vi.doMock(SESSION, () => ({
    useSessionStore: () => ({
      sessionDetails: loggedIn
        ? {
            isLoggedIn: true,
            orgName: "my-org",
            adapters: ["llm", "vector_db", "embedding", "x2text"],
          }
        : { isLoggedIn: false },
    }),
  }));
  if (plugin === null) {
    // No plugins directory: the component's optional import rejects.
    vi.doMock(PLUGIN, () => {
      throw new Error("Cannot find module (OSS build has no plugins)");
    });
  } else {
    vi.doMock(PLUGIN, () => plugin);
  }
  const { RequireGuest } = await import("./RequireGuest.jsx");
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route element={<RequireGuest />}>
          <Route path="/landing" element={<div>landing</div>} />
        </Route>
        <Route path="/my-org/*" element={<div>in-app</div>} />
      </Routes>
    </MemoryRouter>,
  );
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("RequireGuest with a working product plugin", () => {
  it("honours the product named ONLY in the query", async () => {
    // The defect this PR fixes, and the assertion the old empty stub could
    // never make: nothing writes the store on this path, so the query is the
    // visitor's only statement of intent.
    stubLocation();

    await mount({ plugin: PRESENT, url: "/landing?selectedProduct=flow" });

    await vi.waitFor(() => expect(assigned).toEqual(["/flow"]));
    expect(screen.queryByText("in-app")).toBeNull();
  });

  it("prefers the STORED product over the query", async () => {
    // A fallback, not an override: a store that can answer keeps answering.
    stubLocation();

    await mount({
      plugin: PRESENT_WITH_STORED,
      url: "/landing?selectedProduct=unstract",
    });

    await vi.waitFor(() => expect(assigned).toEqual(["/flow"]));
  });

  it("ignores a query product the plugin does not recognise", async () => {
    // The closed-map property, seen from this side: an unrecognised name —
    // including anything someone appends hoping to be redirected to it —
    // leaves the in-app destination standing.
    stubLocation();

    await mount({
      plugin: PRESENT,
      url: "/landing?selectedProduct=https%3A%2F%2Fevil.example",
    });

    expect(await screen.findByText("in-app")).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });

  it("routes in-app when no product is named at all", async () => {
    stubLocation();

    await mount({ plugin: PRESENT, url: "/landing" });

    expect(await screen.findByText("in-app")).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });

  it("leaves a signed-OUT visitor on the guest route", async () => {
    // `/landing` is public, so the external redirect never runs. This is the
    // path omnibench-platform#903's bounce depends on.
    stubLocation();

    await mount({
      plugin: PRESENT,
      loggedIn: false,
      url: "/landing?selectedProduct=flow",
    });

    expect(await screen.findByText("landing")).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });
});

describe("RequireGuest before unstract-cloud#1998 lands", () => {
  it("falls back to today's behaviour when the by-name accessor is missing", async () => {
    // The merge-order safety property, now asserted instead of hand-checked:
    // calling an accessor that does not exist throws into the `try` the
    // lookup already sits in, so the visitor routes exactly as before.
    stubLocation();

    await mount({ plugin: PARTIAL, url: "/landing?selectedProduct=flow" });

    expect(await screen.findByText("in-app")).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });
});

describe("RequireGuest on an OSS-only build", () => {
  it("routes in-app with no plugin present, parameter or not", async () => {
    stubLocation();

    await mount({ plugin: null, url: "/landing?selectedProduct=flow" });

    expect(await screen.findByText("in-app")).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });
});
