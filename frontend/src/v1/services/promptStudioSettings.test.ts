import { QueryClient } from "@tanstack/react-query";
import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
} from "@v1/test";
import {
  ADAPTER_IDS,
  makeProfile,
  makeToolSettings,
  profileFixtures,
  SETTINGS_TOOL_ID,
  settingsHandlers,
  strategyFixtures,
} from "@v1/test/fixtures/promptStudioSettings";
import { afterEach, beforeEach, expect, it } from "vitest";
import { setOrganizationId } from "./context";
import {
  createProfile,
  deleteProfile,
  getAdapterInfo,
  type LlmProfileBody,
  listProfiles,
  listRetrievalStrategies,
  promptProfileKeys,
  promptProfileQueries,
  setDefaultProfile,
  updateProfile,
} from "./promptProfiles";
import {
  getToolSettings,
  promptStudioToolKeys,
  promptStudioToolQueries,
  updateToolSettings,
} from "./promptStudioTool";

const S = DEFAULT_SESSION;
const TOOL = SETTINGS_TOOL_ID;

beforeEach(() => setOrganizationId(S.organization.id));
afterEach(() => setOrganizationId(null));

const body: LlmProfileBody = {
  profile_name: "new",
  llm: ADAPTER_IDS.llm,
  embedding_model: ADAPTER_IDS.embedding,
  vector_store: ADAPTER_IDS.vectorDb,
  x2text: ADAPTER_IDS.x2text,
  chunk_size: 1024,
  chunk_overlap: 128,
  reindex: true,
  retrieval_strategy: "fusion",
  similarity_top_k: 3,
  section: "Default",
  prompt_studio_tool: TOOL,
};

it("reads the project's settings fields", async () => {
  mockApi(...settingsHandlers(S));
  await expect(getToolSettings(TOOL)).resolves.toEqual(makeToolSettings());
});

it("fails at the boundary when the project payload changes shape", async () => {
  mockApi(
    http.get(apiPath(S, `/prompt-studio/${TOOL}/`), () =>
      HttpResponse.json({ ...makeToolSettings(), prompt_grammer: "oops" }),
    ),
  );
  await expect(getToolSettings(TOOL)).rejects.toThrow();
});

it("patches only the fields a section saves", async () => {
  let sent: unknown;
  mockApi(
    http.patch(apiPath(S, `/prompt-studio/${TOOL}/`), async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json(makeToolSettings({ preamble: "P" }));
    }),
  );
  const saved = await updateToolSettings(TOOL, { preamble: "P" });
  expect(sent).toEqual({ preamble: "P" });
  expect(saved.preamble).toBe("P");
});

it("lists profiles with adapter names and ids", async () => {
  mockApi(...settingsHandlers(S));
  await expect(listProfiles(TOOL)).resolves.toEqual(profileFixtures.three);
});

it("accepts a blank retrieval strategy, which the model allows", async () => {
  mockApi(
    ...settingsHandlers(S, {
      profiles: [makeProfile({ retrieval_strategy: "" })],
    }),
  );
  const [row] = await listProfiles(TOOL);
  expect(row?.retrieval_strategy).toBe("");
});

it("sets the default profile and returns its id", async () => {
  let sent: unknown;
  mockApi(
    http.patch(
      apiPath(S, `/prompt-studio/prompt-studio-profile/${TOOL}/`),
      async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ default_profile: "p2" });
      },
    ),
  );
  await expect(setDefaultProfile(TOOL, "p2")).resolves.toBe("p2");
  expect(sent).toEqual({ default_profile: "p2" });
});

it("creates a profile on the slashless profilemanager route", async () => {
  let sent: unknown;
  mockApi(
    http.post(
      apiPath(S, `/prompt-studio/profilemanager/${TOOL}`),
      async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json(makeProfile({ profile_name: "new" }), {
          status: 201,
        });
      },
    ),
  );
  const created = await createProfile(body);
  expect(sent).toEqual(body);
  expect(created.profile_name).toBe("new");
});

it("updates and deletes a profile by id", async () => {
  const id = "p-1";
  const calls: string[] = [];
  mockApi(
    http.put(apiPath(S, `/prompt-studio/profile-manager/${id}/`), () => {
      calls.push("put");
      return HttpResponse.json(makeProfile({ profile_id: id }));
    }),
    http.delete(apiPath(S, `/prompt-studio/profile-manager/${id}/`), () => {
      calls.push("delete");
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await updateProfile(id, body);
  await deleteProfile(id);
  expect(calls).toEqual(["put", "delete"]);
});

it("lists retrieval strategies in the backend's order", async () => {
  mockApi(...settingsHandlers(S));
  await expect(listRetrievalStrategies(TOOL)).resolves.toEqual(
    Object.values(strategyFixtures),
  );
});

it("reads an LLM's context window", async () => {
  mockApi(...settingsHandlers(S));
  await expect(getAdapterInfo(ADAPTER_IDS.llm)).resolves.toEqual({
    id: ADAPTER_IDS.llm,
    context_window_size: 200000,
  });
});

it("keys every query by organisation and fetches through the options", async () => {
  mockApi(...settingsHandlers(S));
  const org = S.organization.id;
  expect(promptStudioToolKeys.detail(TOOL)).toEqual([
    org,
    "prompt-studio-tools",
    "detail",
    TOOL,
  ]);
  expect(promptProfileKeys.list(TOOL)).toEqual([
    org,
    "prompt-profiles",
    "list",
    TOOL,
  ]);
  const client = new QueryClient();
  await expect(
    client.fetchQuery(promptStudioToolQueries.detail(TOOL)),
  ).resolves.toMatchObject({ tool_id: TOOL });
  await expect(
    client.fetchQuery(promptProfileQueries.list(TOOL)),
  ).resolves.toHaveLength(3);
  await expect(
    client.fetchQuery(promptProfileQueries.strategies(TOOL)),
  ).resolves.toHaveLength(2);
  await expect(
    client.fetchQuery(promptProfileQueries.adapterInfo(ADAPTER_IDS.llm)),
  ).resolves.toMatchObject({ context_window_size: 200000 });
});
