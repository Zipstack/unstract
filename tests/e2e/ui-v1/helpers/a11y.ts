/**
 * Accessibility scan with axe (@axe-core/playwright).
 *
 *   await expectAccessible(page);
 *   await expectAccessible(page, { include: ["main"], exclude: ["#chart"] });
 *
 * Scans WCAG 2.0/2.1 A and AA rules and fails on violations at or above
 * `minImpact`. The full results are attached to the report either way.
 *
 * The default level, `serious`, is an ASSUMPTION: the page definition of done
 * says "accessibility scan clean" and P8-T02 owns the final conformance level.
 * UNSTRACT_E2E_A11Y_IMPACT overrides it suite-wide.
 */

import AxeBuilder from "@axe-core/playwright";
import { type Page, test } from "@playwright/test";

export type Impact = "minor" | "moderate" | "serious" | "critical";

const RANK: Record<Impact, number> = {
  minor: 1,
  moderate: 2,
  serious: 3,
  critical: 4,
};

export const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

export interface A11yOptions {
  include?: string[];
  exclude?: string[];
  /** Rule ids to skip; say why next to the call. */
  disableRules?: string[];
  minImpact?: Impact;
  /**
   * `report` attaches and annotates without failing. For scans of v0 screens,
   * which are not held to the v1 bar.
   */
  mode?: "enforce" | "report";
  /** Names the attachment when one test scans more than once. */
  label?: string;
}

function defaultImpact(): Impact {
  const raw = process.env.UNSTRACT_E2E_A11Y_IMPACT?.toLowerCase();
  return raw && raw in RANK ? (raw as Impact) : "serious";
}

export class A11yViolationError extends Error {
  override name = "A11yViolationError";
}

export async function expectAccessible(
  page: Page,
  options: A11yOptions = {},
): Promise<void> {
  const minImpact = options.minImpact ?? defaultImpact();
  let builder = new AxeBuilder({ page }).withTags(WCAG_TAGS);
  for (const selector of options.include ?? []) {
    builder = builder.include(selector);
  }
  for (const selector of options.exclude ?? []) {
    builder = builder.exclude(selector);
  }
  if (options.disableRules?.length) {
    builder = builder.disableRules(options.disableRules);
  }
  const results = await builder.analyze();

  const info = test.info();
  const attachment = options.label ? `axe-${options.label}` : "axe";
  await info.attach(attachment, {
    body: JSON.stringify(results, null, 2),
    contentType: "application/json",
  });

  // axe leaves impact unset only on passes; treat a missing one as blocking.
  const blocking = results.violations.filter(
    (v) => RANK[(v.impact ?? "critical") as Impact] >= RANK[minImpact],
  );
  if (!blocking.length) {
    return;
  }
  const summary = blocking
    .map(
      (v) =>
        `  [${v.impact}] ${v.id}: ${v.help}\n` +
        v.nodes.map((n) => `      ${n.target.join(" ")}`).join("\n"),
    )
    .join("\n");
  const message = `${blocking.length} accessibility violation(s) at or above "${minImpact}":\n${summary}`;

  if (options.mode === "report") {
    info.annotations.push({ type: "a11y (report only)", description: message });
    return;
  }
  throw new A11yViolationError(message);
}
