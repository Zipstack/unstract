import {
  type LlmProfile,
  type LlmProfileBody,
  RETRIEVAL_STRATEGIES,
} from "@v1/services/promptProfiles";
import { z } from "zod";

/*
 * The Add/Edit LLM Profile form: its values (numbers stay strings while
 * typed), the rules, and the mapping to and from the backend.
 */

const WHOLE = /^\d+$/;

const wholeNumber = (min: 0 | 1) =>
  z
    .string()
    .trim()
    .refine((v) => WHOLE.test(v) && Number(v) >= min, {
      message: `Enter a whole number, ${min} or more`,
    })
    .transform(Number);

const required = (message: string) => z.string().trim().min(1, message);

/**
 * The rules. `takenNames` are the other profiles' names in this project;
 * the backend refuses a duplicate on create too (case-sensitive, as checked
 * here), but an edit that collides reaches it only as a server error.
 */
export function profileFormSchema(takenNames: readonly string[]) {
  const taken = new Set(takenNames.map((n) => n.trim()));
  return z
    .object({
      profile_name: required("Enter a name").refine(
        (name) => !taken.has(name),
        "A profile with this name already exists",
      ),
      llm: required("Select an LLM"),
      embedding_model: required("Select an embedding model"),
      vector_store: required("Select a vector database"),
      x2text: required("Select a text extractor"),
      chunk_size: wholeNumber(0),
      chunk_overlap: wholeNumber(0),
      reindex: z.boolean(),
      retrieval_strategy: z.enum(RETRIEVAL_STRATEGIES),
      // Blank means "not set", which the backend stores as null.
      similarity_top_k: z
        .string()
        .trim()
        .refine((v) => v === "" || (WHOLE.test(v) && Number(v) >= 1), {
          message: "Enter a whole number, 1 or more",
        })
        .transform((v) => (v === "" ? null : Number(v))),
      section: z.string().transform((s) => s || null),
    })
    .superRefine((v, ctx) => {
      // Chunk size 0 sends the whole document, so overlap does not apply.
      if (v.chunk_size > 0 && v.chunk_overlap >= v.chunk_size) {
        ctx.addIssue({
          code: "custom",
          path: ["chunk_overlap"],
          message: "Chunk overlap must be smaller than the chunk size",
        });
      }
    });
}

export type ProfileFormSchema = ReturnType<typeof profileFormSchema>;
export type ProfileFormValues = z.input<ProfileFormSchema>;
export type ProfileFormOutput = z.output<ProfileFormSchema>;

/** A new profile, as v0 starts one. */
export const NEW_PROFILE: ProfileFormValues = {
  profile_name: "",
  llm: "",
  embedding_model: "",
  vector_store: "",
  x2text: "",
  chunk_size: "0",
  chunk_overlap: "0",
  reindex: false,
  retrieval_strategy: "simple",
  similarity_top_k: "3",
  section: "Default",
};

const text = (n: number | null) => (n === null ? "" : String(n));

/** A saved profile as form values; adapters by id, since the field holds the name. */
export function profileValues(profile: LlmProfile): ProfileFormValues {
  return {
    profile_name: profile.profile_name,
    llm: profile.llm_id,
    embedding_model: profile.embedding_model_id,
    vector_store: profile.vector_store_id,
    x2text: profile.x2text_id,
    chunk_size: text(profile.chunk_size ?? 0),
    chunk_overlap: text(profile.chunk_overlap ?? 0),
    reindex: profile.reindex,
    retrieval_strategy: profile.retrieval_strategy || "simple",
    similarity_top_k: text(profile.similarity_top_k),
    section: profile.section ?? "",
  };
}

export function toProfileBody(
  values: ProfileFormOutput,
  toolId: string,
): LlmProfileBody {
  return { ...values, prompt_studio_tool: toolId };
}

/** v0's estimate under chunk size: about four characters a token, in thousands. */
export function approxTokens(chunkSize: number): string {
  return `${(chunkSize / 4 / 1024).toFixed(1)}k`;
}
