/** Route-pattern helpers for the registry: the subset of React Router patterns it accepts. */

const PARAM = /^:[A-Za-z_]\w*$/;
const STATIC = /^[A-Za-z0-9._~-]+$/;

function segments(pattern: string): string[] {
  return pattern.split("/").filter((s) => s !== "");
}

/**
 * Why a pattern is not accepted, or null. Accepted: absolute, static
 * segments, `:name` params and a final `*`. Optional segments (`:id?`) are
 * not, so that overlap checking stays exact.
 */
export function patternProblem(pattern: string): string | null {
  if (!pattern.startsWith("/")) {
    return "must start with /";
  }
  const segs = segments(pattern);
  for (const [i, seg] of segs.entries()) {
    if (seg === "*") {
      if (i !== segs.length - 1) {
        return "* is allowed only as the last segment";
      }
    } else if (!PARAM.test(seg) && !STATIC.test(seg)) {
      return `segment '${seg}' is not a static name, :param or a final *`;
    }
  }
  return null;
}

/** The `:name` params of a pattern, plus `*` when it ends in a splat. */
export function paramNames(pattern: string): string[] {
  return segments(pattern)
    .filter((s) => s === "*" || s.startsWith(":"))
    .map((s) => (s === "*" ? "*" : s.slice(1)));
}

/** True when some URL matches both patterns. Static segments compare case-insensitively, as React Router does. */
export function patternsOverlap(a: string, b: string): boolean {
  const sa = segments(a);
  const sb = segments(b);
  for (let i = 0; ; i++) {
    const x = sa[i];
    const y = sb[i];
    if (x === "*" || y === "*") {
      return true; // a splat also matches nothing, so this holds even when the other pattern ended
    }
    if (x === undefined || y === undefined) {
      return x === y;
    }
    if (
      !x.startsWith(":") &&
      !y.startsWith(":") &&
      x.toLowerCase() !== y.toLowerCase()
    ) {
      return false;
    }
  }
}
