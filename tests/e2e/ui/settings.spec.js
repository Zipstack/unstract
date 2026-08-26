import { expect, test } from "./fixtures.js";

/**
 * Adapter settings — the UI side of `adapter-register-llm`.
 *
 * Adapters are a hard prerequisite: with no LLM configured, Prompt Studio and
 * every workflow that calls a model are dead. This asserts each adapter screen
 * loads and offers registration; the credential round-trip itself is covered
 * API-side in integration-backend, where it belongs.
 */

/*
 * `type` is the value the route passes to ToolSettings, which is what the add
 * button's id is built from — the button's LABEL ("New Text Extractor") is
 * per-route copy and the first thing i18n would break.
 */
const ADAPTERS = [
  { route: "settings/llms", type: "llm" },
  { route: "settings/vectorDbs", type: "vector_db" },
  { route: "settings/embedding", type: "embedding" },
  { route: "settings/textExtractor", type: "x2text" },
];

test.describe("adapter settings", () => {
  for (const { route, type } of ADAPTERS) {
    test(`${route} loads and offers registration`, async ({ page, app }) => {
      await app.goto(route);

      await expect(
        page.getByTestId(`${type}-adapter-add-btn`),
        `${route} offers no way to add an adapter`,
      ).toBeVisible({ timeout: 20000 });
    });
  }

  /*
   * Opening the picker is where registration actually begins: it lists the
   * available providers. An empty or absent list means the adapter registry
   * did not load, which is indistinguishable from "no adapters supported".
   */
  test("the LLM picker lists providers to choose from", async ({
    page,
    app,
  }) => {
    await app.goto("settings/llms");
    await page.getByTestId("llm-adapter-add-btn").click();

    const dialog = page.getByTestId("add-source-modal");
    await expect(dialog).toBeVisible({ timeout: 20000 });
    /*
     * Was `img, [class*='card']` — a substring match on a class name, which
     * would match any styled box in the dialog (or nothing, after a restyle).
     * Provider cards now carry an id built from the adapter's own id.
     */
    await expect(
      dialog.locator('[data-testid^="ds-card-"]').first(),
      "provider list did not render",
    ).toBeVisible();
  });
});
