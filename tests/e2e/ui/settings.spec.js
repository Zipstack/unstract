import { expect, test } from "./fixtures.js";

/**
 * Adapter settings — the UI side of `adapter-register-llm`.
 *
 * Adapters are a hard prerequisite: with no LLM configured, Prompt Studio and
 * every workflow that calls a model are dead. This asserts each adapter screen
 * loads and offers registration; the credential round-trip itself is covered
 * API-side in integration-backend, where it belongs.
 */

const ADAPTERS = [
  { route: "settings/llms", button: /New LLM Profile/i },
  { route: "settings/vectorDbs", button: /New Vector DB Profile/i },
  { route: "settings/embedding", button: /New Embedding Profile/i },
  { route: "settings/textExtractor", button: /New Text Extractor/i },
];

test.describe("adapter settings", () => {
  for (const { route, button } of ADAPTERS) {
    test(`${route} loads and offers registration`, async ({ page, app }) => {
      await app.goto(route);

      await expect(
        page.getByRole("button", { name: button }).first(),
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
    await page.getByRole("button", { name: /New LLM Profile/i }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 20000 });
    await expect(
      dialog.locator("img, [class*='card']").first(),
      "provider list did not render",
    ).toBeVisible();
  });
});
