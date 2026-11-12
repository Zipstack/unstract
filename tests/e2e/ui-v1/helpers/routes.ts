/** Route-pattern utilities shared by the redirect and old-version helpers. */

import { paramNames } from "../contract/registry.ts";

export { paramNames };

export type RouteParams = Readonly<Record<string, string>>;

/** A `:name` segment; the registry allows no optional (`:id?`) ones. */
const PARAM = /:([A-Za-z_]\w*)/g;

/** A final splat segment, which the registry allows (patterns.ts). */
const SPLAT = "/*";

/**
 * `/:orgName/workflows/:id` + params -> `/org_1/workflows/42`, as the
 * frontend's fillPattern (registry/resolve.ts, which imports react-router, so
 * it can't be imported here) fills it: each value encoded, and a final `*`
 * taking `params["*"]` with its slashes kept and each segment encoded. An
 * omitted splat leaves no trailing slash.
 */
export function fillPattern(pattern: string, params: RouteParams): string {
  const hasSplat = pattern.endsWith(SPLAT);
  const filled = (hasSplat ? pattern.slice(0, -SPLAT.length) : pattern).replace(
    PARAM,
    (_, name: string) => {
      const value = params[name];
      if (value === undefined) {
        throw new Error(`route ${pattern} needs a value for :${name}`);
      }
      return encodeURIComponent(value);
    },
  );
  const splat = hasSplat ? (params["*"] ?? "") : "";
  if (!splat) {
    return filled;
  }
  return `${filled}/${splat.split("/").map(encodeURIComponent).join("/")}`;
}

/** Whether `params` fills every param `pattern` needs (a splat is optional). */
export function fillable(pattern: string, params: RouteParams): boolean {
  return paramNames(pattern).every(
    (name) => name === "*" || params[name] !== undefined,
  );
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

/**
 * Matches the full URL of a filled route: any origin, an optional trailing
 * slash, then an optional query or hash.
 */
export function routeRegex(path: string): RegExp {
  const trimmed = path.replace(/\/$/, "");
  return new RegExp(`^[a-z]+://[^/]+${escapeRegex(trimmed)}/?([?#].*)?$`);
}
