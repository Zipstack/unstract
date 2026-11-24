import { screen, waitFor, within } from "@testing-library/react";
import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import {
  promptStudioToolKeys,
  type ToolSettings,
} from "@v1/services/promptStudioTool";
import {
  apiPath,
  DEFAULT_SESSION,
  expectNoA11yViolations,
  HttpResponse,
  http,
  mockApi,
  renderV1,
} from "@v1/test";
import {
  makeToolSettings,
  profileFixtures,
  SETTINGS_TOOL_ID,
  settingsHandlers,
} from "@v1/test/fixtures/promptStudioSettings";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsTab, type SettingsTabProps } from "./SettingsTab";

const S = DEFAULT_SESSION;
const TOOL = apiPath(S, `/prompt-studio/${SETTINGS_TOOL_ID}/`);

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

/** Answers the reads, and records each PATCH body of the project. */
function serve(tool: ToolSettings = makeToolSettings()) {
  const patches: unknown[] = [];
  mockApi(
    ...settingsHandlers(S, { tool }),
    http.patch(TOOL, async ({ request }) => {
      const patch = (await request.json()) as Partial<ToolSettings>;
      patches.push(patch);
      return HttpResponse.json({ ...tool, ...patch });
    }),
  );
  return patches;
}

function renderTab(props: Partial<SettingsTabProps> = {}) {
  return renderV1(<SettingsTab toolId={SETTINGS_TOOL_ID} {...props} />);
}

const section = (name: string) => screen.getByRole("region", { name });

async function loaded() {
  await screen.findByRole("region", { name: "Custom Data" });
  await screen.findByRole("cell", { name: "test4" });
}

describe("layout and slot gating", () => {
  it("shows the OSS sections in design order and no cloud ones", async () => {
    serve();
    renderTab();
    await loaded();
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual([
      "LLM Profiles",
      "Custom Data",
      "Grammar",
      "Preamble",
      "Postamble",
    ]);
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent),
    ).toEqual(["LLM Profile Settings", "Custom Data", "Grammar", "Preamble"]);
  });

  it("lists a cloud section when a plugin fills its slot", async () => {
    serve();
    renderTab({
      isSlotFilled: (slot) => slot === "prompt-studio.settings.llm-challenge",
    });
    await loaded();
    const links = within(
      screen.getByRole("navigation", { name: "Settings sections" }),
    ).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toContain("LLM Challenge");
    expect(links.map((a) => a.textContent)).not.toContain("Highlighting");
  });

  it("links each list entry to its section and marks the one chosen", async () => {
    serve();
    const { user } = renderTab();
    await loaded();
    const link = screen.getByRole("link", { name: "Grammar" });
    expect(link).toHaveAttribute("href", "#ps-settings-grammar");
    expect(document.getElementById("ps-settings-grammar")).toBe(
      section("Grammar"),
    );
    expect(document.getElementById("ps-settings-postamble")).not.toBeNull();
    await user.click(link);
    expect(link).toHaveAttribute("aria-current", "location");
  });

  it("has no accessibility violations", async () => {
    serve();
    const { container } = renderTab();
    await loaded();
    // axe cannot build a selector for a disabled button under happy-dom
    // (nthChild of undefined); violations still report, with their HTML.
    await expectNoA11yViolations(container, { selectors: false });
  });
});

describe("project settings sections", () => {
  it("saves the preamble alone and returns to No changes", async () => {
    const patches = serve();
    const { user } = renderTab();
    await loaded();
    const preamble = section("Preamble");
    const box = within(preamble).getByLabelText("Preamble");
    await user.clear(box);
    await user.type(box, "Be brief.");
    expect(within(preamble).getByText("1 unsaved change")).toBeVisible();
    await user.click(
      within(preamble).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(patches).toEqual([{ preamble: "Be brief." }]));
    expect(await within(preamble).findByText("No changes")).toBeVisible();
    // Other sections never saved.
    expect(within(section("Grammar")).getByText("No changes")).toBeVisible();
  });

  it("puts the shipped default back with Reset", async () => {
    serve();
    const { user } = renderTab();
    await loaded();
    const preamble = section("Preamble");
    await user.click(
      within(preamble).getByRole("button", {
        name: "Reset postamble to the default",
      }),
    );
    expect(within(preamble).getByLabelText("Postamble")).toHaveValue(
      "Do not include any explanation in the reply. Only include the extracted information in the reply.",
    );
    expect(within(preamble).getByText("1 unsaved change")).toBeVisible();
  });

  it("adds a custom data pair, nested JSON included", async () => {
    const patches = serve();
    const { user } = renderTab();
    await loaded();
    const data = section("Custom Data");
    await user.click(within(data).getByRole("button", { name: "Add pair" }));
    await user.type(within(data).getByLabelText("Key 4"), "user");
    // `{` is a userEvent key descriptor; `{{` types one brace.
    await user.type(within(data).getByLabelText("Value 4"), '{{"name": "A"}');
    await user.click(
      within(data).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(patches).toEqual([
        {
          custom_data: {
            client_code: "CYB-2026",
            region: "US-EAST",
            fiscal_year: 2026,
            user: { name: "A" },
          },
        },
      ]),
    );
  });

  it("blocks saving custom data with a repeated key", async () => {
    const patches = serve();
    const { user } = renderTab();
    await loaded();
    const data = section("Custom Data");
    await user.click(within(data).getByRole("button", { name: "Add pair" }));
    await user.type(within(data).getByLabelText("Key 4"), "region");
    await user.click(
      within(data).getByRole("button", { name: "Save changes" }),
    );
    expect(
      await within(data).findByText("This key is already used"),
    ).toBeVisible();
    expect(patches).toEqual([]);
  });

  it("checks the variables active prompts use against the unsaved pairs", async () => {
    serve();
    const { user } = renderTab();
    await loaded();
    const data = section("Custom Data");
    expect(within(data).getByText(/1 not defined/)).toBeVisible();
    expect(within(data).queryByText("custom_data.inactive_key")).toBeNull();
    expect(within(data).queryByText("custom_data.note_key")).toBeNull();
    await user.click(within(data).getByRole("button", { name: "Add pair" }));
    await user.type(within(data).getByLabelText("Key 4"), "city");
    await user.type(within(data).getByLabelText("Value 4"), "Pune");
    expect(
      within(data).queryByText(/not defined ·|· 1 not defined/),
    ).toBeNull();
  });

  it("says how to use custom data when no active prompt does", async () => {
    serve(makeToolSettings({ prompts: [] }));
    renderTab();
    await loaded();
    expect(
      within(section("Custom Data")).getByText(
        /No active prompt uses custom data yet/,
      ),
    ).toBeVisible();
  });

  it("removes a grammar word and saves the rest", async () => {
    const patches = serve();
    const { user } = renderTab();
    await loaded();
    const grammar = section("Grammar");
    await user.click(
      within(grammar).getByRole("button", { name: "Remove word 1" }),
    );
    await user.click(
      within(grammar).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(patches).toEqual([{ prompt_grammer: { "Amt.": ["Amount"] } }]),
    );
  });

  it("types a grammar word without dropping characters", async () => {
    serve();
    const { user } = renderTab();
    await loaded();
    const grammar = section("Grammar");
    await user.click(
      within(grammar).getByRole("button", { name: "Add synonym" }),
    );
    const word = within(grammar).getByLabelText("Word 3");
    await user.type(word, "bill");
    expect(word).toHaveValue("bill");
  });

  it("shows a server error in the section's footer", async () => {
    mockApi(
      ...settingsHandlers(S),
      http.patch(TOOL, () =>
        HttpResponse.json(
          {
            type: "validation_error",
            errors: [
              { code: "invalid", detail: "Too long.", attr: "preamble" },
            ],
          },
          { status: 400 },
        ),
      ),
    );
    const { user } = renderTab();
    await loaded();
    const preamble = section("Preamble");
    await user.type(within(preamble).getByLabelText("Preamble"), "!");
    await user.click(
      within(preamble).getByRole("button", { name: "Save changes" }),
    );
    expect(await within(preamble).findByText("Too long.")).toBeVisible();
  });

  it("shows values without save controls when read-only", async () => {
    serve();
    renderTab({ readOnly: true });
    await loaded();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add pair" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Add New LLM Profile" }),
    ).toBeNull();
    expect(
      within(section("Preamble")).getByLabelText("Preamble"),
    ).toHaveAttribute("readonly");
  });

  it("shows an error with Retry when the project cannot load", async () => {
    mockApi(
      ...settingsHandlers(S).slice(1),
      http.get(TOOL, () => HttpResponse.json({}, { status: 500 })),
    );
    renderTab();
    expect(await screen.findByRole("button", { name: "Retry" })).toBeVisible();
  });
});

it("shows the no-permission state when the project is forbidden", async () => {
  mockApi(
    ...settingsHandlers(S).slice(1),
    http.get(TOOL, () =>
      HttpResponse.json(
        {
          type: "client_error",
          errors: [{ code: "permission_denied", detail: "No.", attr: null }],
        },
        { status: 403 },
      ),
    ),
  );
  renderTab();
  expect(
    await screen.findByRole("heading", {
      name: "You don't have access to this page",
    }),
  ).toBeVisible();
  expect(screen.queryByRole("navigation")).toBeNull();
});

describe("leave guard", () => {
  it("asks before leaving only while a section has unsaved changes", async () => {
    serve();
    let canLeave: () => Promise<boolean> = async () => false;
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { user } = renderTab({
      onLeaveGuard: (fn) => {
        canLeave = fn;
      },
    });
    await loaded();
    await expect(canLeave()).resolves.toBe(true);
    expect(ask).not.toHaveBeenCalled();
    await user.type(within(section("Grammar")).getByLabelText("Word 1"), "x");
    await waitFor(async () => expect(await canLeave()).toBe(false));
    expect(ask).toHaveBeenCalled();
  });
});

describe("changing project", () => {
  const OTHER = "9b8c7d6e-5f4a-4b3c-8d2e-1f0a9b8c7d6e";
  const other = makeToolSettings({ tool_id: OTHER, preamble: "Other." });

  function serveBoth() {
    serve();
    mockApi(
      http.get(apiPath(S, `/prompt-studio/${OTHER}/`), () =>
        HttpResponse.json(other),
      ),
      http.get(
        apiPath(S, `/prompt-studio/prompt-studio-profile/${OTHER}/`),
        () => HttpResponse.json([]),
      ),
    );
  }

  it("drops the previous project's unsaved draft", async () => {
    serveBoth();
    let canLeave: () => Promise<boolean> = async () => false;
    const ask = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onLeaveGuard = (fn: () => Promise<boolean>) => {
      canLeave = fn;
    };
    const { user, rerender, queryClient } = renderTab({ onLeaveGuard });
    await loaded();
    queryClient.setQueryData(promptStudioToolKeys.detail(OTHER), other);
    const box = within(section("Preamble")).getByLabelText("Preamble");
    await user.clear(box);
    await user.type(box, "Draft for the first project.");
    rerender(<SettingsTab toolId={OTHER} onLeaveGuard={onLeaveGuard} />);
    expect(
      await within(section("Preamble")).findByDisplayValue("Other."),
    ).toBeVisible();
    await expect(canLeave()).resolves.toBe(true);
    expect(ask).not.toHaveBeenCalled();
  });

  it("closes the profile editor", async () => {
    serveBoth();
    const { user, rerender } = renderTab();
    await loaded();
    const [first] = profileFixtures.three;
    await user.click(
      screen.getByRole("button", { name: `Edit ${first?.profile_name}` }),
    );
    expect(
      screen.getByRole("heading", { name: "Edit LLM Profile" }),
    ).toBeVisible();
    rerender(<SettingsTab toolId={OTHER} />);
    expect(
      await screen.findByRole("heading", { name: "LLM Profile Settings" }),
    ).toBeVisible();
  });
});

it("stops asking once a dirty section is replaced by the no-permission state", async () => {
  let forbidden = false;
  mockApi(
    ...settingsHandlers(S).slice(1),
    http.get(TOOL, () =>
      forbidden
        ? HttpResponse.json(
            {
              type: "client_error",
              errors: [
                { code: "permission_denied", detail: "No.", attr: null },
              ],
            },
            { status: 403 },
          )
        : HttpResponse.json(makeToolSettings()),
    ),
  );
  let canLeave: () => Promise<boolean> = async () => false;
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const { user, queryClient } = renderTab({
    onLeaveGuard: (fn) => {
      canLeave = fn;
    },
  });
  await loaded();
  await user.type(within(section("Grammar")).getByLabelText("Word 1"), "x");
  await waitFor(async () => expect(await canLeave()).toBe(false));
  forbidden = true;
  await queryClient.refetchQueries({
    queryKey: promptStudioToolKeys.detail(SETTINGS_TOOL_ID),
  });
  await screen.findByRole("heading", {
    name: "You don't have access to this page",
  });
  await waitFor(async () => expect(await canLeave()).toBe(true));
});

describe("saving against the cached project", () => {
  const preambleBox = () =>
    within(section("Preamble")).getByLabelText("Preamble");

  it("writes the saved project to the cache", async () => {
    serve();
    const { user, queryClient } = renderTab();
    await loaded();
    await user.clear(preambleBox());
    await user.type(preambleBox(), "Be brief.");
    await user.click(
      within(section("Preamble")).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() =>
      expect(
        queryClient.getQueryData<ToolSettings>(
          promptStudioToolKeys.detail(SETTINGS_TOOL_ID),
        )?.preamble,
      ).toBe("Be brief."),
    );
  });

  it("shows a change made elsewhere unless the section has unsaved changes", async () => {
    let tool = makeToolSettings();
    mockApi(
      ...settingsHandlers(S).slice(1),
      http.get(TOOL, () => HttpResponse.json(tool)),
    );
    const { user, queryClient } = renderTab();
    await loaded();
    const refetch = () =>
      queryClient.refetchQueries({
        queryKey: promptStudioToolKeys.detail(SETTINGS_TOOL_ID),
      });
    tool = makeToolSettings({ preamble: "Changed elsewhere." });
    await refetch();
    await waitFor(() =>
      expect(preambleBox()).toHaveValue("Changed elsewhere."),
    );

    await user.type(preambleBox(), " Mine.");
    tool = makeToolSettings({ preamble: "Changed again." });
    await refetch();
    expect(preambleBox()).toHaveValue("Changed elsewhere. Mine.");

    await user.click(
      within(section("Preamble")).getByRole("button", { name: "Discard" }),
    );
    await waitFor(() => expect(preambleBox()).toHaveValue("Changed again."));
  });

  it("keeps what is typed while a save is in flight", async () => {
    const tool = makeToolSettings();
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockApi(
      ...settingsHandlers(S, { tool }),
      http.patch(TOOL, async ({ request }) => {
        const patch = (await request.json()) as Partial<ToolSettings>;
        await held;
        return HttpResponse.json({ ...tool, ...patch });
      }),
    );
    const { user } = renderTab();
    await loaded();
    await user.clear(preambleBox());
    await user.type(preambleBox(), "Be brief.");
    await user.click(
      within(section("Preamble")).getByRole("button", { name: "Save changes" }),
    );
    await user.type(preambleBox(), " Really.");
    expect(preambleBox()).toHaveValue("Be brief. Really.");
    release();
    await within(section("Preamble")).findByText("1 unsaved change");
    expect(preambleBox()).toHaveValue("Be brief. Really.");
  });

  it("keeps a save when an older read of the project lands after it", async () => {
    const tool = makeToolSettings();
    let release: () => void = () => undefined;
    let hold = false;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockApi(
      ...settingsHandlers(S).slice(1),
      http.get(TOOL, async () => {
        if (hold) {
          await held;
        }
        return HttpResponse.json(tool);
      }),
      http.patch(TOOL, async ({ request }) =>
        HttpResponse.json({
          ...tool,
          ...((await request.json()) as Partial<ToolSettings>),
        }),
      ),
    );
    const { user, queryClient } = renderTab();
    await loaded();
    hold = true;
    void queryClient.refetchQueries({
      queryKey: promptStudioToolKeys.detail(SETTINGS_TOOL_ID),
    });
    await user.clear(preambleBox());
    await user.type(preambleBox(), "Be brief.");
    await user.click(
      within(section("Preamble")).getByRole("button", { name: "Save changes" }),
    );
    await within(section("Preamble")).findByText("No changes");
    release();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(preambleBox()).toHaveValue("Be brief.");
    expect(
      queryClient.getQueryData<ToolSettings>(
        promptStudioToolKeys.detail(SETTINGS_TOOL_ID),
      )?.preamble,
    ).toBe("Be brief.");
  });
});
