import { screen, waitFor, within } from "@testing-library/react";
import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import type { ToolSettings } from "@v1/services/promptStudioTool";
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
    await waitFor(() =>
      expect(patches).toEqual([
        { preamble: "Be brief.", postamble: makeToolSettings().postamble },
      ]),
    );
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

  it("removes a grammar word and saves the rest", async () => {
    const patches = serve();
    const { user } = renderTab();
    await loaded();
    const grammar = section("Grammar");
    await user.click(
      within(grammar).getByRole("button", { name: "Remove BoA" }),
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
