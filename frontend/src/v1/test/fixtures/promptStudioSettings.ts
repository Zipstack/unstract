/*
 * Fixtures for services/promptStudioTool and services/promptProfiles, shaped
 * as the backend renders them: CustomToolSerializer for the project (only the
 * settings fields, plus a few it always sends), ProfileManagerSerializer for
 * profiles (adapter names in the field, ids in `<field>_id`) and
 * get_retrieval_strategy_metadata for strategies (an object keyed by
 * strategy). Shared by the service tests and the Settings tab tests.
 */

import type { Adapter } from "@v1/services/adapters";
import type {
  LlmProfile,
  RetrievalStrategyInfo,
} from "@v1/services/promptProfiles";
import type { ToolSettings } from "@v1/services/promptStudioTool";
import { apiPath, HttpResponse, http, type TestSession } from "@v1/test";

export const SETTINGS_TOOL_ID = "7a2d3f5b-9c4e-4d6f-8a81-2b3c4d5e6f70";

export const ADAPTER_IDS = {
  llm: "11111111-1111-4111-8111-111111111111",
  llm2: "11111111-1111-4111-8111-222222222222",
  embedding: "22222222-2222-4222-8222-222222222222",
  vectorDb: "33333333-3333-4333-8333-333333333333",
  x2text: "44444444-4444-4444-8444-444444444444",
} as const;

const adapter = (
  id: string,
  name: string,
  type: Adapter["adapter_type"],
): Adapter => ({
  id,
  adapter_id: `${name.toLowerCase()}|${id}`,
  adapter_name: name,
  adapter_type: type,
  description: null,
  icon: "",
  created_at: "2026-11-01T10:00:00Z",
  modified_at: "2026-11-01T10:00:00Z",
});

/** One adapter list per type, as `GET adapter/?adapter_type=` answers. */
export const settingsAdapters = {
  LLM: [
    adapter(ADAPTER_IDS.llm, "claude-sonnet-4-6", "LLM"),
    adapter(ADAPTER_IDS.llm2, "gpt-4o", "LLM"),
  ],
  EMBEDDING: [adapter(ADAPTER_IDS.embedding, "az-embed-ada-002", "EMBEDDING")],
  VECTOR_DB: [adapter(ADAPTER_IDS.vectorDb, "postgres neon db", "VECTOR_DB")],
  X2TEXT: [adapter(ADAPTER_IDS.x2text, "LLM Whisperer V2", "X2TEXT")],
  OCR: [],
} satisfies Record<Adapter["adapter_type"], Adapter[]>;

export function makeProfile(overrides: Partial<LlmProfile> = {}): LlmProfile {
  return {
    profile_id: "0b7c9d1e-2f3a-4b5c-8d6e-7f8091a2b3c4",
    profile_name: "test3",
    llm: "claude-sonnet-4-6",
    llm_id: ADAPTER_IDS.llm,
    embedding_model: "az-embed-ada-002",
    embedding_model_id: ADAPTER_IDS.embedding,
    vector_store: "postgres neon db",
    vector_store_id: ADAPTER_IDS.vectorDb,
    x2text: "LLM Whisperer V2",
    x2text_id: ADAPTER_IDS.x2text,
    chunk_size: 0,
    chunk_overlap: 0,
    reindex: false,
    retrieval_strategy: "simple",
    similarity_top_k: 3,
    section: "Default",
    is_default: true,
    ...overrides,
  };
}

export const profileFixtures = {
  three: [
    makeProfile(),
    makeProfile({
      profile_id: "1c8d0e2f-3a4b-4c5d-9e6f-8091a2b3c4d5",
      profile_name: "test",
      llm: "gpt-4o",
      llm_id: ADAPTER_IDS.llm2,
      is_default: false,
    }),
    makeProfile({
      profile_id: "2d9e1f30-4b5c-4d6e-8f70-91a2b3c4d5e6",
      profile_name: "test4",
      chunk_size: 1024,
      chunk_overlap: 128,
      is_default: false,
    }),
  ],
} satisfies Record<string, LlmProfile[]>;

export function makeToolSettings(
  overrides: Partial<ToolSettings> = {},
): ToolSettings {
  return {
    tool_id: SETTINGS_TOOL_ID,
    tool_name: "Sample Credit Card Parser Automation",
    preamble:
      "You are reading a credit card statement issued by a US bank. Amounts are in USD.",
    postamble: "If the value is not present in the document, return null.",
    prompt_grammer: { BoA: ["Bank of America"], "Amt.": ["Amount"] },
    custom_data: {
      client_code: "CYB-2026",
      region: "US-EAST",
      fiscal_year: 2026,
    },
    default_profile: profileFixtures.three[0]?.profile_id,
    prompts: [
      { prompt: "Client {{custom_data.client_code}} in {{custom_data.city}}" },
      {
        prompt: "Ignored {{custom_data.inactive_key}}",
        active: false,
      },
      {
        prompt: "A note about {{custom_data.note_key}}",
        prompt_type: "NOTES",
      },
    ],
    ...overrides,
  };
}

const strategy = (
  key: RetrievalStrategyInfo["key"],
  title: string,
): RetrievalStrategyInfo => ({
  key,
  title,
  description: `${title} description.`,
  best_for: ["Straightforward questions"],
  token_usage: "Low",
  cost_impact: "Low",
  technical_details: "Details.",
});

/** As the backend answers: an object keyed by strategy. */
export const strategyFixtures: Record<string, RetrievalStrategyInfo> = {
  simple: strategy("simple", "Simple Vector Retrieval"),
  fusion: strategy("fusion", "Fusion Retrieval (RAG Fusion)"),
};

/** Every read the Settings tab makes, answered from these fixtures. */
export const settingsHandlers = (
  session: TestSession,
  {
    tool = makeToolSettings(),
    profiles = profileFixtures.three,
  }: Readonly<{ tool?: ToolSettings; profiles?: readonly LlmProfile[] }> = {},
) => [
  http.get(apiPath(session, `/prompt-studio/${SETTINGS_TOOL_ID}/`), () =>
    HttpResponse.json(tool),
  ),
  http.get(
    apiPath(
      session,
      `/prompt-studio/prompt-studio-profile/${SETTINGS_TOOL_ID}/`,
    ),
    () => HttpResponse.json(profiles),
  ),
  http.get(
    apiPath(
      session,
      `/prompt-studio/${SETTINGS_TOOL_ID}/get_retrieval_strategies/`,
    ),
    () => HttpResponse.json(strategyFixtures),
  ),
  http.get(apiPath(session, "/adapter/"), ({ request }) => {
    const type = new URL(request.url).searchParams.get("adapter_type");
    const rows = settingsAdapters[type as Adapter["adapter_type"]] ?? [];
    return HttpResponse.json(rows);
  }),
  http.get(apiPath(session, "/adapter/info/:id/"), ({ params }) =>
    HttpResponse.json({ id: params.id, context_window_size: 200000 }),
  ),
];
