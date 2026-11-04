import { generatePath, matchRoutes, type Params } from "react-router-dom";
import type { Distribution, PageKey, RegistryEntry } from "./types";

/** What the version switch does with a URL. */
export type Resolution =
  | Readonly<{ kind: "v0" }>
  | Readonly<{ kind: "v1"; entry: RegistryEntry }>
  | Readonly<{ kind: "redirect"; to: string }>;

export type ResolveContext = Readonly<{
  /** The pages that are live in this build and session (see activeEntries). */
  entries: readonly RegistryEntry[];
  /**
   * The user's old-version preference: honoured by toggle pages only. `null`
   * while the user is unknown, which leaves a toggle page's v0 URLs on v0 so
   * v0 can load the session (and with it the preference).
   */
  oldVersion: boolean | null;
}>;

type Location = Readonly<{ pathname: string; search?: string; hash?: string }>;

/** The live entries: declared, registered (or previewed) and shipped in this distribution. */
export function activeEntries(
  pages: readonly RegistryEntry[],
  live: ReadonlySet<PageKey>,
  distribution: Distribution,
): RegistryEntry[] {
  return pages.filter(
    (e) => live.has(e.page) && e.distributions.includes(distribution),
  );
}

type Owned = Readonly<{ path: string; entry: RegistryEntry }>;

/** The registry route a pathname lands on; React Router ranks the most specific pattern first. */
function match(
  pathname: string,
  entries: readonly RegistryEntry[],
): { route: Owned; params: Params } | null {
  const routes: Owned[] = entries.flatMap((entry) =>
    [...new Set([...entry.v1Routes, ...entry.replaces])].map((path) => ({
      path,
      entry,
    })),
  );
  const found = matchRoutes(routes, pathname)?.[0];
  return found ? { route: found.route, params: found.params } : null;
}

function redirect(
  target: string,
  params: Params,
  location: Location,
): Resolution {
  return {
    kind: "redirect",
    to: `${generatePath(target, params)}${location.search ?? ""}${location.hash ?? ""}`,
  };
}

/**
 * The resolution rule. An unregistered URL renders v0. A registered page
 * renders v1, and its v0 URLs redirect to their mapped v1 route; except that
 * a toggle page (Human Review) does the reverse while the user has chosen the
 * old version.
 */
export function resolveRoute(
  location: Location,
  ctx: ResolveContext,
): Resolution {
  const found = match(location.pathname, ctx.entries);
  if (!found) {
    return { kind: "v0" };
  }
  const { entry, path } = found.route;
  const isV1 = entry.v1Routes.includes(path);
  const isV0 = entry.replaces.includes(path);

  if (entry.toggle && ctx.oldVersion !== false) {
    if (isV0) {
      return { kind: "v0" };
    }
    if (ctx.oldVersion === true) {
      const target = entry.toV0[path];
      return target ? redirect(target, found.params, location) : { kind: "v0" };
    }
    // Unknown user on a v1-only URL: v1 is the default.
  }
  if (isV1) {
    return { kind: "v1", entry };
  }
  const target = entry.toV1[path];
  return target ? redirect(target, found.params, location) : { kind: "v0" };
}

/**
 * The URL to open a page's v1 route with, in whichever version the user gets:
 * the filled v1 route when the page is live, else its mapped v0 route. Null
 * when the page is not declared or has no v0 mapping for that route.
 */
export function resolvePageUrl(
  page: PageKey,
  v1Pattern: string,
  params: Readonly<Record<string, string>>,
  pages: readonly RegistryEntry[],
  ctx: ResolveContext,
): string | null {
  const entry = pages.find((e) => e.page === page);
  if (!entry?.v1Routes.includes(v1Pattern)) {
    return null;
  }
  const live = ctx.entries.includes(entry);
  const useV0 = !live || (entry.toggle && ctx.oldVersion === true);
  if (!useV0) {
    return generatePath(v1Pattern, params);
  }
  const target = entry.toV0[v1Pattern];
  return target ? generatePath(target, params) : null;
}
