/** Route-pattern utilities shared by the redirect and old-version helpers. */

export type RouteParams = Readonly<Record<string, string>>;

const PARAM = /:([A-Za-z_]\w*)\??/g;

export function paramNames(pattern: string): string[] {
  return [...pattern.matchAll(PARAM)].map((m) => m[1] as string);
}

/** A final splat segment, which the registry allows (patterns.ts). */
const SPLAT = "/*";

/**
 * `/:orgName/workflows/:id` + params -> `/org_1/workflows/42`. A final `*`
 * takes `params["*"]` the way the frontend's fillPattern does: its slashes
 * kept, each segment encoded, and empty when omitted.
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
  if (!hasSplat) {
    return filled;
  }
  const splat = params["*"] ?? "";
  return `${filled}/${splat.split("/").map(encodeURIComponent).join("/")}`;
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
