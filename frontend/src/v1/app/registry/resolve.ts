import { generatePath, matchRoutes, type Params } from "react-router-dom";
import { paramNames } from "./patterns";
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

type RouteLocation = Readonly<{
  pathname: string;
  search?: string;
  hash?: string;
}>;

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
export function matchRegistryRoute(
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

/**
 * Fills a pattern with raw (decoded) param values, encoding each one, so a
 * value holding `/`, `?` or `#` stays inside its segment. A splat keeps its
 * slashes and encodes each of its segments.
 */
export function fillPattern(
  pattern: string,
  params: Readonly<Record<string, string | undefined>>,
): string {
  const encoded: Record<string, string> = {};
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined) {
      encoded[name] =
        name === "*"
          ? value.split("/").map(encodeURIComponent).join("/")
          : encodeURIComponent(value);
    }
  }
  return generatePath(pattern, encoded);
}

function redirect(
  target: string,
  params: Params,
  location: RouteLocation,
): Resolution {
  return {
    kind: "redirect",
    to: `${fillPattern(target, params)}${location.search ?? ""}${location.hash ?? ""}`,
  };
}

/**
 * The resolution rule. An unregistered URL renders v0. A registered page
 * renders v1, and its v0 URLs redirect to their mapped v1 route. A toggle page
 * (Human Review) does the reverse while the user has chosen the old version,
 * and keeps its v0 URLs on v0 while the user is unknown.
 */
export function resolveRoute(
  location: RouteLocation,
  ctx: ResolveContext,
): Resolution {
  const found = matchRegistryRoute(location.pathname, ctx.entries);
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
    // Unknown user on one of the page's v1 URLs: render v1, the default.
  }
  if (isV1) {
    return { kind: "v1", entry };
  }
  const target = entry.toV1[path];
  return target ? redirect(target, found.params, location) : { kind: "v0" };
}

/**
 * The URL that opens a page's v1 route in the version the user gets: the v1
 * URL when the page is live (unless it is a toggle page and the user chose the
 * old version), else its mapped v0 URL. Params are raw values; they are
 * encoded here. Null when the page is not declared, the pattern is not one
 * of its v1 routes, or a `:param` of the pattern is missing or empty (a final
 * `*` may be omitted).
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
  // generatePath throws on a missing param and drops an empty one's segment
  // (`/:orgName/x` with "" gives `/x`), so neither can build a right URL.
  if (paramNames(v1Pattern).some((name) => name !== "*" && !params[name])) {
    return null;
  }
  const live = ctx.entries.some((e) => e.page === page);
  const useV0 = !live || (entry.toggle && ctx.oldVersion === true);
  if (!useV0) {
    return fillPattern(v1Pattern, params);
  }
  const target = entry.toV0[v1Pattern];
  return target ? fillPattern(target, params) : null;
}
