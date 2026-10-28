/**
 * The ONE place the harness learns about the v1 route registry (P0-T03).
 *
 * The redirect and old-version helpers read routes only through this module,
 * so wiring in the real registry is a change to this file alone.
 *
 * Built ahead of P0-T03: the types mirror its published contract table, and
 * `REGISTRY` is empty until the registry exists. When it lands, replace the
 * stub block below with a re-export of the frontend module, then set
 * `REGISTRY_SOURCE` to "frontend". That import only works if the registry
 * module is pure data with plain relative imports: Playwright transpiles TS
 * itself and applies neither Vite (`import.meta.env`, asset imports) nor the
 * frontend tsconfig path aliases. If it cannot be, have P0-T03 emit JSON and
 * read that here instead.
 */

export type Distribution = "oss" | "cloud" | "onprem";

/** UN01 to UN20 (Document Studio), LW01 to LW07 (LLMWhisperer). */
export type PageKey = `UN${string}` | `LW${string}`;

/** Route patterns are React Router patterns, e.g. `/:orgName/workflows/:id`. */
export interface RegistryEntry {
  page: PageKey;
  /** v1 route patterns, including v1-only sub-routes (tabs, stages). */
  v1Routes: readonly string[];
  /** v0 route patterns this page takes over. */
  replaces: readonly string[];
  /** v1 pattern -> v0 pattern; read only by Human Review's old-version mode. */
  toV0: Readonly<Record<string, string>>;
  /** v0 pattern -> v1 pattern it redirects to. */
  toV1: Readonly<Record<string, string>>;
  /** Honours the old-version preference. True for UN11 only (D14). */
  toggle: boolean;
  distributions: readonly Distribution[];
  /** The go-live task that registers the page, e.g. "P4-T01". */
  registeredBy: string;
}

export type RegistrySource = "stub" | "frontend";

// ── stub: replace this block when P0-T03 lands ───────────────────────────────
export const REGISTRY_SOURCE: RegistrySource = "stub";
export const REGISTRY: readonly RegistryEntry[] = stubRegistry();
function stubRegistry(): readonly RegistryEntry[] {
  return [];
}
/**
 * Where the Human Review old-version preference lives. P0-T03 says per user,
 * per browser, no backend, so browser storage; the key itself is a
 * placeholder until P0-T03 names it.
 */
export const OLD_VERSION_PREFERENCE = {
  storage: "localStorage",
  key: "unstract.v1.humanReview.oldVersion",
  on: "true",
} as const;
/**
 * How a test asks the app to render a page's v1 routes BEFORE it is
 * registered. Under D9 only a page's final task registers it, so every
 * earlier task's spec needs this. P0-T03 has not defined it yet; `null` makes
 * every spec that asks for a preview skip. Expected shape once it exists: a
 * dev/test-only storage key or cookie holding the page keys to preview,
 * honoured only in non-production builds.
 */
export const V1_PREVIEW: PreviewMechanism | null = null;
// ── end stub ────────────────────────────────────────────────────────────────

export type PreviewMechanism =
  | { kind: "localStorage" | "sessionStorage"; key: string }
  | { kind: "cookie"; name: string };

export const PREVIEW_PENDING_REASON =
  "P0-T03 has no dev/test override to render an unregistered v1 page: contract/registry.ts V1_PREVIEW=null";

export const REGISTRY_PENDING_REASON =
  "P0-T03 route registry not landed: contract/registry.ts REGISTRY_SOURCE=stub";

export function registryAvailable(): boolean {
  return REGISTRY_SOURCE !== "stub";
}

export function findEntry(page: PageKey): RegistryEntry {
  const entry = REGISTRY.find((e) => e.page === page);
  if (!entry) {
    throw new Error(
      `page ${page} is not in the route registry (source=${REGISTRY_SOURCE})`,
    );
  }
  return entry;
}
