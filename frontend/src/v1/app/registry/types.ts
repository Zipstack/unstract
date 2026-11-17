/*
 * Route registry types (UN-4271).
 *
 * This folder's data files (types.ts, entries.ts) import only each other, with
 * `./`, and never touch `import.meta.env`, so a Playwright E2E harness (no
 * Vite, no `@v1` alias) can import them; P0-T09 (UN-4345) wires one in. The
 * same holds for `lib/oldVersion.ts` (the old-version preference keys), which
 * imports nothing. Keep it that way: `live.ts` reads `import.meta.env` when it
 * loads, so a key the harness needs is declared here, not there.
 */

/**
 * Dev/test override: a JSON array of declared page keys to render as v1
 * before they are registered (D9), e.g. `["UN05"]`, read when the app loads.
 * Honoured only with VITE_V1_DEV_ROUTES=true.
 */
export const PREVIEW_STORAGE_KEY = "unstract.v1.preview";

/** The builds the frontend ships in. */
export const DISTRIBUTIONS = ["oss", "cloud", "onprem"] as const;

export type Distribution = (typeof DISTRIBUTIONS)[number];

/**
 * Target page key: UN01 to UN20 (Unstract), LW01 to LW07 (LLMWhisperer), or a
 * development-only demo page (`DEMO-…`) that is live only when
 * VITE_V1_DEV_ROUTES is on. The exact format is checked by registryProblems.
 */
export type PageKey = `UN${string}` | `LW${string}` | `DEMO-${string}`;

/**
 * One v1 page. Route patterns are absolute React Router patterns
 * (`/:orgName/workflows/:id`); a trailing `/*` matches the rest of the URL.
 */
export type RegistryEntry = Readonly<{
  page: PageKey;
  /** The v1 route patterns, including v1-only sub-routes (tabs, stages). */
  v1Routes: readonly string[];
  /** The v0 route patterns this page takes over. */
  replaces: readonly string[];
  /**
   * v1 pattern -> the v0 pattern it maps back to; covers every v1 route. Used
   * by Human Review's old-version mode, and by resolveUrl while the page is
   * not live. A v1-only sub-route maps to the nearest v0 route.
   */
  toV0: Readonly<Record<string, string>>;
  /** v0 pattern -> the v1 pattern it redirects to; covers every `replaces` pattern. */
  toV1: Readonly<Record<string, string>>;
  /**
   * Honours the old-version preference. Allowed only for UN11 (Human Review,
   * D14) and its demo stand-in; see TOGGLE_PAGES.
   */
  toggle: boolean;
  /** Builds the page exists in; an entry the current build lacks is ignored. */
  distributions: readonly Distribution[];
  /** The go-live task that registers the page, e.g. "P6-T07". */
  registeredBy: string;
}>;
