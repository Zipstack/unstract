import { screen, waitFor, within } from "@testing-library/react";
import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import type { LlmProfile } from "@v1/services/promptProfiles";
import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
  renderV1,
} from "@v1/test";
import {
  ADAPTER_IDS,
  makeProfile,
  profileFixtures,
  SETTINGS_TOOL_ID,
  settingsHandlers,
} from "@v1/test/fixtures/promptStudioSettings";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ProfilesSection } from "./ProfilesSection";

const S = DEFAULT_SESSION;
const LIST = apiPath(
  S,
  `/prompt-studio/prompt-studio-profile/${SETTINGS_TOOL_ID}/`,
);
const CREATE = apiPath(S, `/prompt-studio/profilemanager/${SETTINGS_TOOL_ID}`);
const one = (id: string) => apiPath(S, `/prompt-studio/profile-manager/${id}/`);
const [first, second] = profileFixtures.three as [LlmProfile, LlmProfile];

let shown: NotifyInput[] = [];
let unregister: () => void = () => undefined;
beforeEach(() => {
  shown = [];
  unregister = setNotifier({
    show: (input) => {
      shown.push(input);
      return String(shown.length);
    },
    dismiss: () => undefined,
  });
});
afterEach(() => unregister());

/** The list endpoint answers whatever `rows` holds now; returns a setter. */
function serveProfiles(initial: readonly LlmProfile[] = profileFixtures.three) {
  let rows = initial;
  mockApi(
    http.get(LIST, () => HttpResponse.json(rows)),
    ...settingsHandlers(S).filter((_, i) => i !== 1),
  );
  return (next: readonly LlmProfile[]) => {
    rows = next;
  };
}

function renderSection(onDirtyChange = vi.fn()) {
  const view = renderV1(
    <ProfilesSection
      toolId={SETTINGS_TOOL_ID}
      readOnly={false}
      onDirtyChange={onDirtyChange}
    />,
  );
  return { ...view, onDirtyChange };
}

async function fillNewProfile(
  user: ReturnType<typeof renderSection>["user"],
  name = "prod",
) {
  await user.type(screen.getByLabelText("Name"), name);
  await user.selectOptions(
    await screen.findByLabelText("LLM"),
    await screen.findByRole("option", { name: "gpt-4o" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Embedding Model"),
    await screen.findByRole("option", { name: "az-embed-ada-002" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Vector Database"),
    await screen.findByRole("option", { name: "postgres neon db" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Text Extractor"),
    await screen.findByRole("option", { name: "LLM Whisperer V2" }),
  );
}

it("lists each profile with its adapters and marks the default", async () => {
  serveProfiles();
  renderSection();
  const row = (await screen.findByRole("cell", { name: "test" })).closest("tr");
  expect(row).not.toBeNull();
  expect(
    within(row as HTMLElement)
      .getAllByRole("cell")
      .slice(0, 5)
      .map((c) => c.textContent),
  ).toEqual([
    "test",
    "gpt-4o",
    "az-embed-ada-002",
    "postgres neon db",
    "LLM Whisperer V2",
  ]);
  expect(
    screen.getByRole("radio", { name: "Make test3 the default" }),
  ).toBeChecked();
});

it("shows an empty state when the project has no profiles", async () => {
  serveProfiles([]);
  renderSection();
  expect(await screen.findByText(/No LLM profiles yet/)).toBeVisible();
});

it("makes another profile the default", async () => {
  serveProfiles();
  let sent: unknown;
  mockApi(
    http.patch(LIST, async ({ request }) => {
      sent = await request.json();
      return HttpResponse.json({ default_profile: second.profile_id });
    }),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("radio", { name: "Make test the default" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("radio", { name: "Make test the default" }),
    ).toBeChecked(),
  );
  expect(sent).toEqual({ default_profile: second.profile_id });
});

it("never offers to delete the default profile", async () => {
  serveProfiles();
  renderSection();
  expect(
    await screen.findByRole("button", {
      name: "test3 is the default and cannot be deleted",
    }),
  ).toBeDisabled();
});

it("deletes a profile after confirming, and not without", async () => {
  const setRows = serveProfiles();
  const deleted: string[] = [];
  mockApi(
    http.delete(one(second.profile_id), () => {
      deleted.push(second.profile_id);
      setRows([first]);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  const ask = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
  const { user } = renderSection();
  const remove = await screen.findByRole("button", { name: "Delete test" });
  await user.click(remove);
  expect(deleted).toEqual([]);
  ask.mockReturnValueOnce(true);
  await user.click(remove);
  await waitFor(() =>
    expect(screen.queryByRole("cell", { name: "test" })).toBeNull(),
  );
  expect(deleted).toEqual([second.profile_id]);
});

it("adds a profile, checking chunk overlap against chunk size first", async () => {
  const setRows = serveProfiles();
  let sent: Record<string, unknown> | undefined;
  mockApi(
    http.post(CREATE, async ({ request }) => {
      sent = (await request.json()) as Record<string, unknown>;
      const created = makeProfile({
        profile_id: "new-id",
        profile_name: "prod",
        is_default: false,
      });
      setRows([...profileFixtures.three, created]);
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  const { user, onDirtyChange } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  expect(
    screen.getByRole("region", { name: "Add New LLM Profile" }),
  ).toBeVisible();
  expect(onDirtyChange).toHaveBeenLastCalledWith(false);
  await fillNewProfile(user);
  expect(onDirtyChange).toHaveBeenLastCalledWith(true);
  const size = screen.getByLabelText("Chunk size");
  const overlap = screen.getByLabelText("Chunk overlap");
  await user.clear(size);
  await user.type(size, "1024");
  await user.clear(overlap);
  await user.type(overlap, "1024");
  await user.click(screen.getByLabelText("Reindex on save"));
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  expect(
    await screen.findByText(
      "Chunk overlap must be smaller than the chunk size",
    ),
  ).toBeVisible();
  expect(sent).toBeUndefined();
  await user.clear(overlap);
  await user.type(overlap, "128");
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await screen.findByRole("cell", { name: "prod" });
  expect(sent).toEqual({
    profile_name: "prod",
    llm: ADAPTER_IDS.llm2,
    embedding_model: ADAPTER_IDS.embedding,
    vector_store: ADAPTER_IDS.vectorDb,
    x2text: ADAPTER_IDS.x2text,
    chunk_size: 1024,
    chunk_overlap: 128,
    reindex: true,
    retrieval_strategy: "simple",
    similarity_top_k: 3,
    section: "Default",
    prompt_studio_tool: SETTINGS_TOOL_ID,
  });
  expect(shown.map((n) => n.title)).toContain("Profile saved");
  expect(onDirtyChange).toHaveBeenLastCalledWith(false);
});

it("makes a project's first profile its default", async () => {
  const setRows = serveProfiles([]);
  let defaulted: unknown;
  mockApi(
    http.post(CREATE, () => {
      const created = makeProfile({ profile_id: "first", is_default: false });
      setRows([created]);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(LIST, async ({ request }) => {
      defaulted = await request.json();
      return HttpResponse.json({ default_profile: "first" });
    }),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user, "first");
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() => expect(defaulted).toEqual({ default_profile: "first" }));
});

it("refreshes the list only after the first profile is the default", async () => {
  const events: string[] = [];
  let rows: readonly LlmProfile[] = [];
  mockApi(
    http.get(LIST, () => {
      events.push("list");
      return HttpResponse.json(rows);
    }),
    ...settingsHandlers(S).filter((_, i) => i !== 1),
    http.post(CREATE, () => {
      const created = makeProfile({ profile_id: "first", is_default: false });
      rows = [{ ...created, is_default: true }];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(LIST, async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
      events.push("default");
      return HttpResponse.json({ default_profile: "first" });
    }),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user, "first");
  events.length = 0;
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() => expect(events).toContain("list"));
  expect(events[0]).toBe("default");
});

it("says so when the first profile could not be made the default", async () => {
  const setRows = serveProfiles([]);
  mockApi(
    http.post(CREATE, () => {
      const created = makeProfile({
        profile_id: "first",
        profile_name: "first",
        is_default: false,
      });
      setRows([created]);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(LIST, () => HttpResponse.json({}, { status: 500 })),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user, "first");
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() =>
    expect(shown.map((n) => n.title)).toContain(
      "Profile saved, but it is not the default",
    ),
  );
  expect(await screen.findByRole("cell", { name: "first" })).toBeVisible();
});

it("refuses a name another profile of the project has", async () => {
  serveProfiles();
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user, "test4");
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  expect(
    await screen.findByText("A profile with this name already exists"),
  ).toBeVisible();
});

it("warns instead of confirming when the LLM may not read images", async () => {
  serveProfiles();
  mockApi(
    http.post(CREATE, () =>
      HttpResponse.json(
        makeProfile({ profile_id: "v", vision_warning: "No vision support." }),
        { status: 201 },
      ),
    ),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user);
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() =>
    expect(shown).toContainEqual(
      expect.objectContaining({
        kind: "warning",
        description: "No vision support.",
      }),
    ),
  );
});

it("shows the backend's refusal in the form", async () => {
  serveProfiles();
  mockApi(
    http.post(CREATE, () =>
      HttpResponse.json(
        {
          type: "client_error",
          errors: [
            {
              code: "permission_denied",
              detail:
                "Maximum number of profiles (max 4) per prompt studio project has been reached.",
              attr: null,
            },
          ],
        },
        { status: 403 },
      ),
    ),
  );
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  await fillNewProfile(user);
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  expect(await screen.findByText(/Maximum number of profiles/)).toBeVisible();
});

it("stops adding at four profiles", async () => {
  serveProfiles([
    ...profileFixtures.three,
    makeProfile({ profile_id: "p4", profile_name: "four", is_default: false }),
  ]);
  renderSection();
  expect(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  ).toBeDisabled();
  expect(screen.getByText("A project has at most 4 profiles.")).toBeVisible();
});

it("edits a profile by its adapter ids and keeps one the user cannot see", async () => {
  serveProfiles([
    makeProfile({
      x2text: "Unshared extractor",
      x2text_id: "99999999-9999-4999-8999-999999999999",
      chunk_size: 1024,
      chunk_overlap: 128,
    }),
  ]);
  let sent: Record<string, unknown> | undefined;
  mockApi(
    http.put(one(first.profile_id), async ({ request }) => {
      sent = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(makeProfile());
    }),
  );
  const { user } = renderSection();
  await user.click(await screen.findByRole("button", { name: "Edit test3" }));
  expect(
    screen.getByRole("region", { name: "Edit LLM Profile" }),
  ).toBeVisible();
  expect(screen.getByLabelText("Name")).toHaveValue("test3");
  await waitFor(() =>
    expect(screen.getByLabelText("LLM")).toHaveValue(ADAPTER_IDS.llm),
  );
  expect(
    screen.getByRole("option", { name: "Unshared extractor" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Matching count limit")).toHaveValue("3");
  expect(await screen.findByText(/LLM context 200000/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  await waitFor(() =>
    expect(sent).toMatchObject({
      x2text: "99999999-9999-4999-8999-999999999999",
      chunk_size: 1024,
    }),
  );
});

it("goes back to the list on Cancel", async () => {
  serveProfiles();
  const { user } = renderSection();
  await user.click(await screen.findByRole("button", { name: "Edit test" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await screen.findByRole("cell", { name: "test4" })).toBeVisible();
});

it("shows the strategy's description and opens Advanced settings with an error", async () => {
  serveProfiles();
  const { user } = renderSection();
  await user.click(
    await screen.findByRole("button", { name: "Add New LLM Profile" }),
  );
  expect(screen.queryByLabelText("Retrieval strategy")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Advanced settings" }));
  await user.selectOptions(
    screen.getByLabelText("Retrieval strategy"),
    await screen.findByRole("option", {
      name: "Fusion Retrieval (RAG Fusion)",
    }),
  );
  expect(
    screen.getByText(/Fusion Retrieval \(RAG Fusion\) description\./),
  ).toBeVisible();
  const topK = screen.getByLabelText("Matching count limit");
  await user.clear(topK);
  await user.type(topK, "0");
  await user.click(screen.getByRole("button", { name: "Advanced settings" }));
  await fillNewProfile(user);
  await user.click(screen.getByRole("button", { name: "Save profile" }));
  expect(
    await screen.findByText("Enter a whole number, 1 or more"),
  ).toBeVisible();
});
