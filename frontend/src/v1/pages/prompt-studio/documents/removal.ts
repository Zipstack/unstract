/** A prompt's coverage: the ids of the documents it has output for. */
export type PromptCoverage = Readonly<{ coverage: readonly string[] }>;

const WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
];

const number = (count: number) => WORDS[count] ?? String(count);

const REMOVED =
  "The document and every prompt output produced from it are removed.";

/**
 * The remove confirm's text (frame D08). Coverage comes from the prompts on
 * the page; without it, or when no prompt covers the document, only the
 * first sentence shows. The count is out of the documents before removal,
 * as the frame words it ("drops to 3 of 4").
 */
export function removalDescription(
  documentId: string,
  documentCount: number,
  prompts: readonly PromptCoverage[] | undefined,
): string {
  const all = prompts ?? [];
  const losing = all.filter((prompt) => prompt.coverage.includes(documentId));
  if (losing.length === 0) {
    return REMOVED;
  }
  const after = new Set(losing.map((prompt) => prompt.coverage.length - 1));
  if (losing.length === all.length && after.size === 1) {
    const [covered] = after;
    const subject =
      all.length === 1 ? "the prompt" : `all ${number(all.length)} prompts`;
    return `${REMOVED} Coverage for ${subject} drops to ${covered} of ${documentCount}.`;
  }
  return `${REMOVED} Coverage drops by one document for ${number(losing.length)} of ${number(all.length)} prompts.`;
}
