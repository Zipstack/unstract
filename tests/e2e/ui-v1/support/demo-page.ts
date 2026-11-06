/**
 * STAND-IN for P0-T03's development-only demo route. Not the version switch.
 *
 * P0-T03 proves its switch with "a demo page registered under a
 * development-only route". That route does not exist yet, so the harness
 * self-tests and the demo spec serve this page instead: `page.route` fulfils
 * `/__v1-demo` on the frontend origin with a minimal page that follows the
 * contract/v1-ui.ts markers (v1 root, state test ids, theme hook) and loads
 * its data from `/__v1-demo/api/items`. A green run here proves the helpers,
 * not the switch. Replace it with the real demo route once P0-T03 lands.
 */

import type { Page, Route } from "@playwright/test";
import { STATE_TEST_IDS, THEME_ATTRIBUTE } from "../contract/v1-ui.ts";

export const DEMO_PATH = "/__v1-demo";
export const DEMO_API = "**/__v1-demo/api/items";

export interface DemoItems {
  items: { id: string; name: string }[];
}

export const DEMO_REST: DemoItems = {
  items: [
    { id: "1", name: "Invoice extraction" },
    { id: "2", name: "Bank statements" },
  ],
};

export const DEMO_EMPTY: DemoItems = { items: [] };

/** Rest-state list; the page's only data-bearing element. */
export const DEMO_REST_TEST_ID = "demo-rest";

const T = STATE_TEST_IDS;

const HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>v1 harness demo</title>
<style>
  :root { --bg: #ffffff; --fg: #1a1a1a; --muted: #4a4a4a; }
  html[${THEME_ATTRIBUTE}="dark"] { --bg: #111418; --fg: #f2f2f2; --muted: #c4c4c4; }
  html[${THEME_ATTRIBUTE}="unstract"] { --bg: #0b2545; --fg: #ffffff; --muted: #d6e4f0; }
  body { margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--fg); }
  main { padding: 24px; }
  p { color: var(--muted); }
</style>
</head>
<body>
<main data-ui-version="v1">
  <h1>Demo items</h1>
  <div id="slot"></div>
</main>
<script>
  const slot = document.getElementById("slot");
  const show = (html) => { slot.innerHTML = html; };
  show('<div data-testid="${T.loading}" role="status" aria-live="polite"><p>Loading items</p></div>');
  fetch("${DEMO_PATH}/api/items")
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
      list.dataset.testid = "${DEMO_REST_TEST_ID}";
      list.setAttribute("aria-label", "Demo items");
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
 * Serves the stand-in page and a default rest response for its API. A route
 * added later (e.g. by expectFiveStates) takes precedence over this one.
 */
export async function installDemoPage(
  page: Page,
  rest: DemoItems = DEMO_REST,
): Promise<void> {
  await page.route(`**${DEMO_PATH}`, (route: Route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: HTML }),
  );
  await page.route(DEMO_API, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(rest),
    }),
  );
}

export async function openDemoPage(page: Page): Promise<void> {
  await page.goto(DEMO_PATH, { waitUntil: "domcontentloaded" });
}
