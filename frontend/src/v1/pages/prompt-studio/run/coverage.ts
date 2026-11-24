import type { PromptOutput } from "@v1/services/promptOutputs";

/*
 * Coverage: which documents each prompt has an output for in the current
 * mode. The card's "Coverage: N of N docs" and the export gate read it.
 * The caller passes the prompts that count (enabled, not notes).
 */

export type CoverageDocument = Readonly<{
  documentId: string;
  documentName: string;
}>;

export type CoveragePrompt = Readonly<{
  promptId: string;
  /** Count only this profile's outputs; any profile when left out. */
  profileId?: string;
}>;

export type PromptCoverage = Readonly<{
  covered: number;
  total: number;
  /** The documents this prompt has not run on, in project order. */
  missing: readonly CoverageDocument[];
}>;

export type ToolCoverage = Readonly<{
  byPrompt: Readonly<Record<string, PromptCoverage>>;
  /** At least one prompt and one document, and every prompt covers every document: export may go ahead. */
  complete: boolean;
  /** Prompt x document pairs not run yet. */
  missingCount: number;
}>;

export type CoverageInput = Readonly<{
  prompts: readonly CoveragePrompt[];
  documents: readonly CoverageDocument[];
  rows: readonly PromptOutput[];
  singlePass: boolean;
}>;

export function computeCoverage({
  prompts,
  documents,
  rows,
  singlePass,
}: CoverageInput): ToolCoverage {
  const byPrompt = Object.fromEntries(
    prompts.map(({ promptId, profileId }) => {
      const covered = new Set(
        rows
          .filter(
            (row) =>
              row.prompt_id === promptId &&
              row.is_single_pass_extract === singlePass &&
              (profileId === undefined || row.profile_manager === profileId),
          )
          .map((row) => row.document_manager),
      );
      const missing = documents.filter((d) => !covered.has(d.documentId));
      const coverage: PromptCoverage = {
        covered: documents.length - missing.length,
        total: documents.length,
        missing,
      };
      return [promptId, coverage];
    }),
  );
  const missingCount = Object.values(byPrompt).reduce(
    (sum, c) => sum + c.missing.length,
    0,
  );
  const complete =
    prompts.length > 0 && documents.length > 0 && missingCount === 0;
  return { byPrompt, complete, missingCount };
}

/** "a.pdf", "a.pdf and b.pdf", or "a.pdf, b.pdf and 3 more". */
export function describeMissing(missing: readonly CoverageDocument[]): string {
  const names = missing.map((d) => d.documentName);
  if (names.length <= 2) {
    return names.join(" and ");
  }
  return `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`;
}
