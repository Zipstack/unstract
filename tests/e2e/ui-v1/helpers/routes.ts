/** Route-pattern utilities shared by the redirect and old-version helpers. */

import type { RoutePattern } from "../contract/registry.ts";

export type RouteParams = Readonly<Record<string, string>>;

const PARAM = /:([A-Za-z_][A-Za-z0-9_]*)\??/g;

export function paramNames(pattern: RoutePattern): string[] {
  return [...pattern.matchAll(PARAM)].map((m) => m[1] as string);
}

/** `/:orgName/workflows/:id` + params -> `/org_1/workflows/42`. */
export function fillPattern(
  pattern: RoutePattern,
  params: RouteParams,
): string {
  return pattern.replace(PARAM, (_, name: string) => {
    const value = params[name];
    if (value === undefined) {
      throw new Error(`route ${pattern} needs a value for :${name}`);
    }
    return encodeURIComponent(value);
  });
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Matches the full URL of a filled route: any origin, an optional trailing
 * slash, then an optional query or hash.
 */
export function routeRegex(path: string): RegExp {
  const trimmed = path.replace(/\/$/, "");
  return new RegExp(`^[a-z]+://[^/]+${escapeRegex(trimmed)}/?([?#].*)?$`);
}
