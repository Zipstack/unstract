/*
 * Route registry types (UN-4271).
 *
 * This folder's data files (types.ts, entries.ts) import only each other, with
 * `./`, and never touch `import.meta.env`: the E2E harness imports them from
 * Playwright, which applies neither Vite nor the `@v1` alias.
 */

/** A build the frontend ships in. */
export type Distribution = "oss" | "cloud" | "onprem";

export const DISTRIBUTIONS: readonly Distribution[] = [
  "oss",
  "cloud",
  "onprem",
];

/**
 * Target page key: UN01 to UN20 (Unstract), LW01 to LW07 (LLMWhisperer), or a
 * development-only demo page (`DEMO-…`) that exists only when
 * VITE_V1_DEV_ROUTES is on.
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
   * v1 pattern -> the v0 pattern it maps back to. Read by Human Review's
   * old-version mode, so a toggle page maps every v1 route; a v1-only
   * sub-route maps to the nearest v0 route.
   */
  toV0: Readonly<Record<string, string>>;
  /** v0 pattern -> the v1 pattern it redirects to; covers every `replaces` pattern. */
  toV1: Readonly<Record<string, string>>;
  /** Honours the old-version preference. True for UN11 (Human Review) only, D14. */
  toggle: boolean;
  /** Builds the page exists in; an entry the current build lacks is ignored. */
  distributions: readonly Distribution[];
  /** The go-live task that registers the page, e.g. "P6-T07". */
  registeredBy: string;
}>;
