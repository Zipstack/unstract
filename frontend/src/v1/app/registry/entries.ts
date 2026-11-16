/*
 * The route registry data (UN-4271). Pure data: see the note in ./types.ts.
 *
 * A page is declared in PAGES once its v1 routes exist, and goes live when
 * its go-live task adds its key to REGISTERED_PAGES (D9). Going live, and
 * reverting it, is that one line.
 */

import type { PageKey, RegistryEntry } from "./types";

/** Every declared v1 page, live or not. */
export const PAGES: readonly RegistryEntry[] = [];

/** The pages users get as v1 (D9): a page's go-live task adds its key here. */
export const REGISTERED_PAGES: readonly PageKey[] = [];

/**
 * Development-only demo pages that prove the switch. Registered only in a
 * build with VITE_V1_DEV_ROUTES=true (the E2E image), never in a release.
 * Their v0 side is the stand-in rendered by routes/Router.jsx.
 */
export const DEMO_PAGES: readonly RegistryEntry[] = [
  {
    page: "DEMO-PAGE",
    v1Routes: ["/:orgName/v1-demo"],
    replaces: ["/:orgName/v0-demo"],
    toV0: { "/:orgName/v1-demo": "/:orgName/v0-demo" },
    toV1: { "/:orgName/v0-demo": "/:orgName/v1-demo" },
    toggle: false,
    distributions: ["oss", "cloud", "onprem"],
    registeredBy: "P0-T03",
  },
  {
    // Shaped like Human Review: honours the old-version preference, and has
    // a v1-only sub-route that maps back to the nearest v0 route.
    page: "DEMO-REVIEW",
    v1Routes: ["/:orgName/v1-demo-review", "/:orgName/v1-demo-review/details"],
    replaces: ["/:orgName/v0-demo-review"],
    toV0: {
      "/:orgName/v1-demo-review": "/:orgName/v0-demo-review",
      "/:orgName/v1-demo-review/details": "/:orgName/v0-demo-review",
    },
    toV1: { "/:orgName/v0-demo-review": "/:orgName/v1-demo-review" },
    toggle: true,
    distributions: ["oss", "cloud", "onprem"],
    registeredBy: "P0-T03",
  },
];
