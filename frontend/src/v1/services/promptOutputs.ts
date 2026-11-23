import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { currentOrganizationId } from "./context";
import { http, orgPath, type RequestOptions } from "./http";

/*
 * Prompt Studio outputs: the rows `GET prompt-studio/prompt-output/` returns,
 * which the completed run event also carries inline. One schema covers both,
 * so a contract change fails here and not inside the model grid.
 */

// The socket path serialises Decimal cost as a string; the REST path as a number.
const numberLike = z
  .union([z.number(), z.string()])
  .nullish()
  .transform((value) => {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  });

/** Aggregated usage of the run that wrote the row; `{}` when none was recorded. */
export const tokenUsageSchema = z.looseObject({
  embedding_tokens: numberLike,
  prompt_tokens: numberLike,
  completion_tokens: numberLike,
  total_tokens: numberLike,
  cost_in_dollars: numberLike,
});
export type TokenUsage = z.infer<typeof tokenUsageSchema>;

/** A row of `GET prompt-output/`; extra keys (cloud enrichment) are kept. */
export const promptOutputSchema = z.looseObject({
  prompt_output_id: z.string(),
  prompt_id: z.string(),
  document_manager: z.string(),
  profile_manager: z.string(),
  tool_id: z.string().optional(),
  run_id: z.string().nullish(),
  output: z.string().nullable(),
  is_single_pass_extract: z.boolean(),
  context: z.unknown().optional(),
  highlight_data: z.unknown().optional(),
  token_usage: tokenUsageSchema.catch({
    embedding_tokens: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cost_in_dollars: null,
  }),
  // Document ids; the serializer sends `{}` when it could not compute them.
  coverage: z
    .union([z.array(z.string()), z.record(z.string(), z.unknown())])
    .optional()
    .transform((value) => (Array.isArray(value) ? value : [])),
});
export type PromptOutput = z.infer<typeof promptOutputSchema>;

export const promptOutputListSchema = z.array(promptOutputSchema);

/** Which outputs to list; everything but the tool is an optional filter. */
export type PromptOutputParams = Readonly<{
  toolId: string;
  documentId?: string;
  promptId?: string;
  profileId?: string;
  singlePass?: boolean;
}>;

/** `GET /api/v1/unstract/<org>/prompt-studio/prompt-output/`. */
export async function listPromptOutputs(
  params: PromptOutputParams,
  { signal, org }: RequestOptions = {},
): Promise<PromptOutput[]> {
  const { data } = await http.get<unknown>(
    orgPath("/prompt-studio/prompt-output/", org),
    {
      params: {
        tool_id: params.toolId,
        document_manager: params.documentId,
        prompt_id: params.promptId,
        profile_manager: params.profileId,
        is_single_pass_extract: params.singlePass,
      },
      signal,
    },
  );
  return promptOutputListSchema.parse(data);
}

/** Does a row belong in the list these params select? */
export function matchesOutputParams(
  row: PromptOutput,
  params: PromptOutputParams,
): boolean {
  return (
    (params.documentId === undefined ||
      row.document_manager === params.documentId) &&
    (params.promptId === undefined || row.prompt_id === params.promptId) &&
    (params.profileId === undefined ||
      row.profile_manager === params.profileId) &&
    (params.singlePass === undefined ||
      row.is_single_pass_extract === params.singlePass)
  );
}

const sameSlot = (a: PromptOutput, b: PromptOutput) =>
  a.prompt_id === b.prompt_id &&
  a.document_manager === b.document_manager &&
  a.profile_manager === b.profile_manager &&
  a.is_single_pass_extract === b.is_single_pass_extract;

/**
 * A list with `incoming` rows merged in: a row replaces the one for the same
 * prompt, document, profile and mode; rows the params exclude are skipped.
 */
export function mergePromptOutputs(
  current: readonly PromptOutput[],
  incoming: readonly PromptOutput[],
  params: PromptOutputParams,
): PromptOutput[] {
  const fresh = incoming.filter((row) => matchesOutputParams(row, params));
  const kept = current.filter(
    (row) => !fresh.some((next) => sameSlot(row, next)),
  );
  return [...kept, ...fresh];
}

/** Query keys: `[org, "prompt-outputs", "list", params]`. */
export const promptOutputKeys = {
  all: () => [currentOrganizationId(), "prompt-outputs"] as const,
  list: (params: PromptOutputParams) =>
    [...promptOutputKeys.all(), "list", params] as const,
};

export const promptOutputQueries = {
  list: (params: PromptOutputParams) =>
    queryOptions({
      queryKey: promptOutputKeys.list(params),
      queryFn: ({ queryKey: [org], signal }) =>
        listPromptOutputs(params, { signal, org }),
    }),
};
