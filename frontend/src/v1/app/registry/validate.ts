import { paramNames, patternProblem, patternsOverlap } from "./patterns";
import type { PageKey, RegistryEntry } from "./types";

/** Pages allowed to honour the old-version preference: Human Review (D14) and its demo stand-in. */
export const TOGGLE_PAGES: readonly PageKey[] = ["UN11", "DEMO-REVIEW"];

function checkMapping(
  entry: RegistryEntry,
  name: "toV0" | "toV1",
  from: readonly string[],
  to: readonly string[],
  problems: string[],
): void {
  for (const [source, target] of Object.entries(entry[name])) {
    if (!from.includes(source)) {
      problems.push(
        `${entry.page}: ${name} key ${source} is not one of its routes`,
      );
    }
    if (!to.includes(target)) {
      problems.push(
        `${entry.page}: ${name}[${source}] -> ${target} is not one of its routes`,
      );
    }
    // A splat may be empty, so a target ending in `*` needs nothing from the source.
    const available = [...paramNames(source), "*"];
    const missing = paramNames(target).filter((p) => !available.includes(p));
    if (missing.length) {
      problems.push(
        `${entry.page}: ${name}[${source}] -> ${target} needs params ${source} lacks: ${missing.join(", ")}`,
      );
    }
  }
}

function checkEntry(entry: RegistryEntry, problems: string[]): void {
  const { page, v1Routes, replaces } = entry;
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
  if (entry.toggle && !TOGGLE_PAGES.includes(page)) {
    problems.push(
      `${page}: only Human Review (UN11) may honour the old-version preference (D14)`,
    );
  }
  checkMapping(entry, "toV1", replaces, v1Routes, problems);
  checkMapping(entry, "toV0", v1Routes, replaces, problems);
  for (const pattern of replaces) {
    if (!(pattern in entry.toV1)) {
      problems.push(
        `${page}: v0 route ${pattern} has no v1 route to redirect to`,
      );
    }
  }
  if (entry.toggle) {
    for (const pattern of v1Routes) {
      if (!(pattern in entry.toV0)) {
        problems.push(
          `${page}: v1 route ${pattern} has no v0 route for old-version mode`,
        );
      }
    }
  }
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
  // Two pages may share a prefix (the longest match wins), but no URL may match both.
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
