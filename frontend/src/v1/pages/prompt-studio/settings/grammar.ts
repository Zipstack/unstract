import { z } from "zod";

/*
 * Grammar: words and the phrases the model is told to treat as equal to
 * them, saved as `prompt_grammer` ({word: [equivalents]}). Equivalents are
 * typed comma-separated; a loaded row keeps its list while its text is
 * unchanged, so a stored phrase with a comma survives a save.
 */

/** v0's cap on rows. */
export const GRAMMAR_LIMIT = 200;

/** `loaded` is the stored list, kept so an unchanged row saves as it came. */
export type GrammarRow = {
  word: string;
  synonyms: string;
  loaded?: readonly string[];
};

const SEPARATOR = ", ";

export function grammarRows(
  grammar: Readonly<Record<string, readonly string[]>> | null,
): GrammarRow[] {
  return Object.entries(grammar ?? {}).map(([word, synonyms]) => ({
    word,
    synonyms: synonyms.join(SEPARATOR),
    loaded: synonyms,
  }));
}

/** The comma-separated equivalents, trimmed, each once. */
export function splitSynonyms(text: string): string[] {
  return [
    ...new Set(
      text
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
}

/** The row's equivalents: the stored list while unchanged, else the typed text split. */
function rowSynonyms(row: GrammarRow): readonly string[] {
  return row.loaded !== undefined && row.synonyms === row.loaded.join(SEPARATOR)
    ? row.loaded
    : splitSynonyms(row.synonyms);
}

const isBlank = (row: GrammarRow) =>
  row.word.trim() === "" && splitSynonyms(row.synonyms).length === 0;

export const grammarFormSchema = z
  .object({
    rows: z.array(
      z.object({
        word: z.string(),
        synonyms: z.string(),
        loaded: z.array(z.string()).readonly().optional(),
      }),
    ),
  })
  .superRefine(({ rows }, ctx) => {
    const filled = rows.filter((row) => !isBlank(row));
    if (filled.length > GRAMMAR_LIMIT) {
      ctx.addIssue({
        code: "custom",
        path: ["rows"],
        message: `Up to ${GRAMMAR_LIMIT} words. Remove ${filled.length - GRAMMAR_LIMIT} to save.`,
      });
    }
    const seen = new Set<string>();
    rows.forEach((row, index) => {
      if (isBlank(row)) {
        return;
      }
      const word = row.word.trim();
      if (word === "") {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "word"],
          message: "Enter a word",
        });
      } else if (seen.has(word)) {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "word"],
          message: "This word is already listed",
        });
      }
      seen.add(word);
      if (splitSynonyms(row.synonyms).length === 0) {
        ctx.addIssue({
          code: "custom",
          path: ["rows", index, "synonyms"],
          message: "Add at least one equivalent",
        });
      }
    });
  })
  .transform(({ rows }) => ({
    prompt_grammer: Object.fromEntries(
      rows
        .filter((row) => !isBlank(row))
        .map((row) => [row.word.trim(), [...rowSynonyms(row)]]),
    ),
  }));

export type GrammarValues = z.input<typeof grammarFormSchema>;
