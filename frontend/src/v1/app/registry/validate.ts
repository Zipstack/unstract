import { paramNames, patternProblem, patternsOverlap } from "./patterns";
import type { PageKey, RegistryEntry } from "./types";

/** Pages allowed to honour the old-version preference: Human Review (D14) and its demo stand-in. */
export const TOGGLE_PAGES: readonly PageKey[] = ["UN11", "DEMO-REVIEW"];

const PAGE_KEY = /^(UN(0[1-9]|1\d|20)|LW0[1-7]|DEMO-[A-Z0-9]+(-[A-Z0-9]+)*)$/;

/** True for UN01–UN20, LW01–LW07 and `DEMO-…` keys. */
export function isPageKey(value: unknown): value is PageKey {
  return typeof value === "string" && PAGE_KEY.test(value);
}

function checkMapping(
  entry: RegistryEntry,
  name: "toV0" | "toV1",
  from: readonly string[],
  to: readonly string[],
  problems: string[],
): void {
  for (const [source, target] of Object.entries(entry[name])) {
    const where = `${entry.page}: ${name}[${source}] -> ${target}`;
    if (!from.includes(source)) {
      problems.push(
        `${entry.page}: ${name} key ${source} is not one of its routes`,
      );
    }
    if (!to.includes(target)) {
      problems.push(`${where} is not one of its routes`);
      continue;
    }
    // A splat may be empty, so a target ending in `*` needs nothing from the source.
    const available = new Set([...paramNames(source), "*"]);
    const missing = paramNames(target).filter((p) => !available.has(p));
    if (missing.length) {
      problems.push(
        `${where} needs params ${source} lacks: ${missing.join(", ")}`,
      );
    }
  }
}

/** The entry's own fields: key, pattern syntax, and that it has routes and distributions. */
function checkShape(entry: RegistryEntry, problems: string[]): void {
  const { page, v1Routes, replaces } = entry;
  if (!isPageKey(page)) {
    problems.push(`${page}: not a page key (UN01–UN20, LW01–LW07 or DEMO-…)`);
  }
  for (const pattern of [...v1Routes, ...replaces]) {
    const problem = patternProblem(pattern);
    if (problem) {
      problems.push(`${page}: route ${pattern} ${problem}`);
    }
  }
  if (!v1Routes.length) {
    problems.push(`${page}: has no v1 routes`);
  }
  if (!entry.distributions.length) {
    problems.push(`${page}: ships in no distribution`);
  }
}

function checkToggle(entry: RegistryEntry, problems: string[]): void {
  if (entry.toggle && !TOGGLE_PAGES.includes(entry.page)) {
    problems.push(
      `${entry.page}: only Human Review (UN11) may honour the old-version preference (D14)`,
    );
  }
}

/**
 * A URL matching both a v1 route and a different v0 route of the page is
 * ambiguous: the more specific pattern wins, so a redirect can land on the
 * other version and bounce on to the wrong screen, or back, forever.
 * Identical patterns (the page keeps its v0 URL) are fine.
 */
function checkSamePageOverlap(entry: RegistryEntry, problems: string[]): void {
  for (const v1 of entry.v1Routes) {
    for (const v0 of entry.replaces) {
      if (v1 !== v0 && patternsOverlap(v1, v0)) {
        problems.push(`${entry.page}: v1 route ${v1} overlaps v0 route ${v0}`);
      }
    }
  }
}

/** Every route in `routes` has a key in the `name` mapping. */
function checkCoverage(
  entry: RegistryEntry,
  name: "toV0" | "toV1",
  routes: readonly string[],
  missing: (pattern: string) => string,
  problems: string[],
): void {
  for (const pattern of routes) {
    if (!(pattern in entry[name])) {
      problems.push(`${entry.page}: ${missing(pattern)}`);
    }
  }
}

function checkEntry(entry: RegistryEntry, problems: string[]): void {
  const { v1Routes, replaces } = entry;
  checkShape(entry, problems);
  checkToggle(entry, problems);
  checkSamePageOverlap(entry, problems);
  checkMapping(entry, "toV1", replaces, v1Routes, problems);
  checkMapping(entry, "toV0", v1Routes, replaces, problems);
  checkCoverage(
    entry,
    "toV1",
    replaces,
    (p) => `v0 route ${p} has no v1 route to redirect to`,
    problems,
  );
  // Every v1 route maps back: Human Review's old-version mode needs it, and
  // so does resolveUrl for a page that is declared but not live yet.
  checkCoverage(
    entry,
    "toV0",
    v1Routes,
    (p) => `v1 route ${p} has no v0 route to map back to`,
    problems,
  );
}

/**
 * Every problem with a registry, as readable lines; empty when it is valid.
 * Run over the real registry by its unit test, so a bad entry fails CI.
 */
export function registryProblems(entries: readonly RegistryEntry[]): string[] {
  const problems: string[] = [];
  const seen = new Set<PageKey>();
  for (const entry of entries) {
    if (seen.has(entry.page)) {
      problems.push(`${entry.page}: declared twice`);
    }
    seen.add(entry.page);
    checkEntry(entry, problems);
  }
  // Two pages may share a prefix (/:o/workflows and /:o/workflows/logs), but
  // no URL may match patterns of both.
  const owned = entries.flatMap((entry) =>
    [...new Set([...entry.v1Routes, ...entry.replaces])].map((pattern) => ({
      page: entry.page,
      pattern,
    })),
  );
  for (const [i, a] of owned.entries()) {
    for (const b of owned.slice(i + 1)) {
      if (a.page !== b.page && patternsOverlap(a.pattern, b.pattern)) {
        problems.push(`${a.page} ${a.pattern} overlaps ${b.page} ${b.pattern}`);
      }
    }
  }
  return problems;
}
