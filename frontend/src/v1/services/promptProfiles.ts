import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { currentOrganizationId } from "./context";
import { http, orgPath, type RequestOptions } from "./http";

/*
 * A Prompt Studio project's LLM profiles: list, default, create, edit,
 * delete, the retrieval strategies a profile can use, and an LLM's context
 * window. Responses are parsed here, so a contract change fails at this
 * boundary.
 */

/** The backend caps a project at four profiles (403 past it). */
export const MAX_PROFILES = 4;

export const RETRIEVAL_STRATEGIES = [
  "simple",
  "subquestion",
  "fusion",
  "recursive",
  "router",
  "keyword_table",
  "automerging",
] as const;
export type RetrievalStrategy = (typeof RETRIEVAL_STRATEGIES)[number];

/**
 * A profile as the backend renders it: each adapter field holds the
 * adapter's name, and `<field>_id` its id.
 */
export const llmProfileSchema = z.object({
  profile_id: z.string(),
  profile_name: z.string(),
  llm: z.string(),
  llm_id: z.string(),
  embedding_model: z.string(),
  embedding_model_id: z.string(),
  vector_store: z.string(),
  vector_store_id: z.string(),
  x2text: z.string(),
  x2text_id: z.string(),
  chunk_size: z.number().int().nullable(),
  chunk_overlap: z.number().int().nullable(),
  reindex: z.boolean(),
  /** Blank is allowed by the model; it means the default, simple. */
  retrieval_strategy: z.union([z.enum(RETRIEVAL_STRATEGIES), z.literal("")]),
  similarity_top_k: z.number().int().nullable(),
  section: z.string().nullable(),
  is_default: z.boolean(),
  /** Cloud only: the LLM may not read images in the chosen output mode. */
  vision_warning: z.string().optional(),
});
export type LlmProfile = z.infer<typeof llmProfileSchema>;

/** What create and edit send; adapter fields carry ids. */
export type LlmProfileBody = Readonly<{
  profile_name: string;
  llm: string;
  embedding_model: string;
  vector_store: string;
  x2text: string;
  chunk_size: number;
  chunk_overlap: number;
  reindex: boolean;
  retrieval_strategy: RetrievalStrategy;
  similarity_top_k: number | null;
  section: string | null;
  prompt_studio_tool: string;
}>;

/** One entry of `get_retrieval_strategies`, keyed by strategy in the response. */
export const retrievalStrategyInfoSchema = z.object({
  key: z.enum(RETRIEVAL_STRATEGIES),
  title: z.string(),
  description: z.string(),
  best_for: z.array(z.string()),
  token_usage: z.string(),
  cost_impact: z.string(),
  technical_details: z.string(),
});
export type RetrievalStrategyInfo = z.infer<typeof retrievalStrategyInfoSchema>;

const strategiesSchema = z.record(z.string(), retrievalStrategyInfoSchema);

/** `GET adapter/info/<id>/`: the part the profile form reads. */
export const adapterInfoSchema = z.object({
  id: z.string(),
  context_window_size: z.number().int().nonnegative(),
});
export type AdapterInfo = z.infer<typeof adapterInfoSchema>;

const enc = encodeURIComponent;
const profilesPath = (toolId: string) =>
  `/prompt-studio/prompt-studio-profile/${enc(toolId)}/` as const;
const profilePath = (profileId: string) =>
  `/prompt-studio/profile-manager/${enc(profileId)}/` as const;

/** `GET prompt-studio/prompt-studio-profile/<tool>/`. */
export async function listProfiles(
  toolId: string,
  { signal, org }: RequestOptions = {},
): Promise<LlmProfile[]> {
  const { data } = await http.get<unknown>(orgPath(profilesPath(toolId), org), {
    signal,
  });
  return z.array(llmProfileSchema).parse(data);
}

/** `PATCH prompt-studio/prompt-studio-profile/<tool>/`; returns the new default's id. */
export async function setDefaultProfile(
  toolId: string,
  profileId: string,
  { signal, org }: RequestOptions = {},
): Promise<string> {
  const { data } = await http.patch<unknown>(
    orgPath(profilesPath(toolId), org),
    { default_profile: profileId },
    { signal },
  );
  return z.object({ default_profile: z.string() }).parse(data).default_profile;
}

/** `POST prompt-studio/profilemanager/<tool>` (the route has no trailing slash). */
export async function createProfile(
  body: LlmProfileBody,
  { signal, org }: RequestOptions = {},
): Promise<LlmProfile> {
  const { data } = await http.post<unknown>(
    orgPath(
      `/prompt-studio/profilemanager/${enc(body.prompt_studio_tool)}`,
      org,
    ),
    body,
    { signal },
  );
  return llmProfileSchema.parse(data);
}

/** `PUT prompt-studio/profile-manager/<profile>/`. */
export async function updateProfile(
  profileId: string,
  body: LlmProfileBody,
  { signal, org }: RequestOptions = {},
): Promise<LlmProfile> {
  const { data } = await http.put<unknown>(
    orgPath(profilePath(profileId), org),
    body,
    { signal },
  );
  return llmProfileSchema.parse(data);
}

/** `DELETE prompt-studio/profile-manager/<profile>/`. */
export async function deleteProfile(
  profileId: string,
  { signal, org }: RequestOptions = {},
): Promise<void> {
  await http.delete(orgPath(profilePath(profileId), org), { signal });
}

/** `GET prompt-studio/<tool>/get_retrieval_strategies/`, in the backend's order. */
export async function listRetrievalStrategies(
  toolId: string,
  { signal, org }: RequestOptions = {},
): Promise<RetrievalStrategyInfo[]> {
  const { data } = await http.get<unknown>(
    orgPath(`/prompt-studio/${enc(toolId)}/get_retrieval_strategies/`, org),
    { signal },
  );
  return Object.values(strategiesSchema.parse(data));
}

/** `GET adapter/info/<adapter>/`. */
export async function getAdapterInfo(
  adapterId: string,
  { signal, org }: RequestOptions = {},
): Promise<AdapterInfo> {
  const { data } = await http.get<unknown>(
    orgPath(`/adapter/info/${enc(adapterId)}/`, org),
    { signal },
  );
  return adapterInfoSchema.parse(data);
}

/** Query keys: `[org, "prompt-profiles" | "retrieval-strategies" | "adapter-info", ...]`. */
export const promptProfileKeys = {
  all: () => [currentOrganizationId(), "prompt-profiles"] as const,
  list: (toolId: string) =>
    [...promptProfileKeys.all(), "list", toolId] as const,
  strategies: (toolId: string) =>
    [currentOrganizationId(), "retrieval-strategies", "list", toolId] as const,
  adapterInfo: (adapterId: string) =>
    [currentOrganizationId(), "adapter-info", "detail", adapterId] as const,
};

export const promptProfileQueries = {
  list: (toolId: string) =>
    queryOptions({
      queryKey: promptProfileKeys.list(toolId),
      queryFn: ({ queryKey: [org], signal }) =>
        listProfiles(toolId, { signal, org }),
    }),
  strategies: (toolId: string) =>
    queryOptions({
      queryKey: promptProfileKeys.strategies(toolId),
      queryFn: ({ queryKey: [org], signal }) =>
        listRetrievalStrategies(toolId, { signal, org }),
      // Static metadata shipped with the backend.
      staleTime: Number.POSITIVE_INFINITY,
    }),
  adapterInfo: (adapterId: string) =>
    queryOptions({
      queryKey: promptProfileKeys.adapterInfo(adapterId),
      queryFn: ({ queryKey: [org], signal }) =>
        getAdapterInfo(adapterId, { signal, org }),
    }),
};
