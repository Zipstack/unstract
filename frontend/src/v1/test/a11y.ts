import axe from "axe-core";
import { expect } from "vitest";

/*
 * Accessibility assertions on axe-core. Two rules are off by default:
 * `color-contrast` (tests load no CSS, so every colour is the browser
 * default) and `region` (a component rendered alone is not inside a page's
 * landmarks). Pass `rules` to turn either back on for a whole-page test.
 */

export type A11yOptions = axe.RunOptions;

const DEFAULT_RULES: NonNullable<axe.RunOptions["rules"]> = {
  "color-contrast": { enabled: false },
  region: { enabled: false },
};

// axe-core allows one run at a time ("Axe is already running"), so runs are
// chained: overlapping assertions wait their turn instead of throwing.
let queue: Promise<unknown> = Promise.resolve();

/** Runs axe over `target` and returns its violations. */
export function axeViolations(
  target: Element = document.body,
  options: A11yOptions = {},
): Promise<axe.Result[]> {
  const run = queue.then(async () => {
    const results = await axe.run(target, {
      ...options,
      rules: { ...DEFAULT_RULES, ...options.rules },
    });
    return results.violations;
  });
  queue = run.catch(() => undefined);
  return run;
}

/** One line per failing node: rule, impact, selector and axe's summary. */
export function formatViolations(violations: readonly axe.Result[]): string {
  return violations
    .flatMap((violation) =>
      violation.nodes.map(
        (node) =>
          `  [${violation.id}] (${violation.impact ?? "unknown"}) ${node.target.join(" ")}: ${violation.help}\n    ${violation.helpUrl}`,
      ),
    )
    .join("\n");
}

/** Throws, listing every violation, when axe finds any in `target`. */
export async function expectNoA11yViolations(
  target: Element = document.body,
  options: A11yOptions = {},
): Promise<void> {
  const violations = await axeViolations(target, options);
  if (violations.length > 0) {
    throw new Error(
      `Expected no accessibility violations, found:\n${formatViolations(violations)}`,
    );
  }
}

type A11yMatcherResult = { pass: boolean; message: () => string };

async function toHaveNoA11yViolations(
  received: unknown,
  options: A11yOptions = {},
): Promise<A11yMatcherResult> {
  if (!(received instanceof Element)) {
    return {
      pass: false,
      message: () => "toHaveNoA11yViolations expects a DOM element",
    };
  }
  const violations = await axeViolations(received, options);
  return {
    pass: violations.length === 0,
    message: () =>
      violations.length === 0
        ? "Expected accessibility violations, found none"
        : `Expected no accessibility violations, found:\n${formatViolations(violations)}`,
  };
}

/** Registers `await expect(element).toHaveNoA11yViolations()`; setup.ts calls it. */
export function registerA11yMatchers(): void {
  expect.extend({ toHaveNoA11yViolations });
}

interface A11yMatchers<R = unknown> {
  toHaveNoA11yViolations(options?: A11yOptions): Promise<R>;
}

declare module "vitest" {
  interface Assertion<T> extends A11yMatchers<T> {}
  interface AsymmetricMatchersContaining extends A11yMatchers {}
}
