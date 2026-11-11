/**
 * A self-test fixture for the helpers, not an app page.
 *
 * `expectFiveStates` needs a screen that loads data, and P0-T03's demo pages
 * (`/:orgName/v1-demo`) render static content. So the helper self-tests serve
 * this page instead: `page.route` fulfils `/__v1-harness-fixture` on the
 * frontend origin with a minimal page that renders each state from its API
 * (`/__v1-harness-fixture/api/items`), using the contract/v1-ui.ts markers.
 * A green run here proves the helpers; the version switch is proven against
 * the real demo pages (specs/P0-T09.demo.spec.ts).
 */

import type { Page, Route } from "@playwright/test";
import { STATE_TEST_IDS } from "../contract/v1-ui.ts";

export const FIXTURE_PATH = "/__v1-harness-fixture";
export const FIXTURE_API = "**/__v1-harness-fixture/api/items";

export interface FixtureItems {
  items: { id: string; name: string }[];
}

export const FIXTURE_REST: FixtureItems = {
  items: [
    { id: "1", name: "Invoice extraction" },
    { id: "2", name: "Bank statements" },
  ],
};

export const FIXTURE_EMPTY: FixtureItems = { items: [] };

/** Rest-state list; the page's only data-bearing element. */
export const FIXTURE_REST_TEST_ID = "fixture-rest";

/** Always rendered, whatever the state. */
export const FIXTURE_HEADING_TEST_ID = "fixture-heading";

const T = STATE_TEST_IDS;

const HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>v1 harness fixture</title>
</head>
<body>
<main data-ui-version="v1" data-theme="light">
  <h1 data-testid="${FIXTURE_HEADING_TEST_ID}">Fixture items</h1>
  <div id="slot"></div>
</main>
<script>
  const slot = document.getElementById("slot");
  const show = (html) => { slot.innerHTML = html; };
  show('<div data-testid="${T.loading}" role="status" aria-live="polite"><p>Loading items</p></div>');
  fetch("${FIXTURE_PATH}/api/items")
    .then(async (res) => {
      if (res.status === 403) {
        return show('<section data-testid="${T.noPermission}"><h2>No access</h2><p>You do not have permission to view these items.</p></section>');
      }
      if (!res.ok) {
        return show('<section data-testid="${T.error}" role="alert"><h2>Something went wrong</h2><p>The items could not be loaded.</p></section>');
      }
      const { items } = await res.json();
      if (!items.length) {
        return show('<section data-testid="${T.empty}"><h2>No items yet</h2><p>Items you create appear here.</p></section>');
      }
      const list = document.createElement("ul");
      list.dataset.testid = "${FIXTURE_REST_TEST_ID}";
      list.setAttribute("aria-label", "Fixture items");
      for (const item of items) {
        const li = document.createElement("li");
        li.textContent = item.name;
        list.append(li);
      }
      slot.replaceChildren(list);
    })
    .catch(() => show('<section data-testid="${T.error}" role="alert"><h2>Something went wrong</h2></section>'));
</script>
</body>
</html>`;

/**
 * Serves the fixture page and a default rest response for its API. A route
 * added later (e.g. by expectFiveStates) takes precedence over this one.
 */
export async function installStateFixture(
  page: Page,
  rest: FixtureItems = FIXTURE_REST,
): Promise<void> {
  await page.route(`**${FIXTURE_PATH}`, (route: Route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: HTML }),
  );
  await page.route(FIXTURE_API, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(rest),
    }),
  );
}

export async function openStateFixture(page: Page): Promise<void> {
  await page.goto(FIXTURE_PATH, { waitUntil: "domcontentloaded" });
}
