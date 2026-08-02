import {
  expect,
  expectNoHorizontalOverflow,
  test,
} from "./fixtures.js";

/**
 * Dashboard: Overview / Usage by Deployment / Subscription.
 *
 * Four migration regressions landed on this page, all invisible to jsdom:
 * antd's preset Tag colours rendered as solid fills, `<Col xs={24}>` got no
 * width at all, the nested usage tabs lost their icons, and the RangePicker's
 * nav arrows anchored to the wrong month.
 */
test.describe("dashboard", () => {
  test("renders without horizontal overflow", async ({ page, app }) => {
    await app.goto("dashboard");
    await expect(page.getByText("Dashboard").first()).toBeVisible();
    await expectNoHorizontalOverflow(page, "dashboard");
  });

  /*
   * antd's preset tags are TINTED — pale background, saturated text, mid-tone
   * border. Mapping them onto shadcn Badge variants produced solid fills, so
   * the trial badge was white-on-brown where the reference draws pale amber.
   */
  test("preset Tag colours render as tinted chips, not solid fills", async ({
    page,
    app,
  }) => {
    await app.goto("dashboard");
    const tag = page.locator(".ant-tag").first();
    if ((await tag.count()) === 0) {
      test.skip(true, "no tags on this dashboard");
    }

    const style = await tag.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { bg: cs.backgroundColor, fg: cs.color };
    });

    // A tinted chip is light-on-dark-text; a solid fill is the inverse. Compare
    // luminance rather than exact colours so the assertion survives a palette
    // change but still catches a fill.
    const lum = (c) => {
      const [r, g, b] = c.match(/\d+/g).map(Number);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    expect(
      lum(style.bg),
      `tag background ${style.bg} is not a pale tint`,
    ).toBeGreaterThan(lum(style.fg));
  });

  /*
   * `<Col xs={24}>` must fill its row. The responsive breakpoint props were not
   * destructured, so they hit the DOM as unknown attributes and the column got
   * no width — the usage card shrank to 452px inside a 1447px row.
   */
  test("a full-width Col fills its row", async ({ page, app }) => {
    await app.goto("dashboard");
    const tab = page.getByRole("tab", { name: /Usage by Deployment/i });
    if ((await tab.count()) === 0) {
      test.skip(true, "usage tab not present");
    }
    await tab.click();
    await page.waitForLoadState("networkidle").catch(() => {});

    const ratio = await page.evaluate(() => {
      const col = document.querySelector("[role=tabpanel]:not([hidden]) .ant-col");
      if (!col) return null;
      const row = col.parentElement;
      return col.getBoundingClientRect().width / row.getBoundingClientRect().width;
    });
    if (ratio === null) {
      test.skip(true, "no grid column rendered");
    }
    expect(ratio, "a full-width Col does not fill its row").toBeGreaterThan(0.9);
  });

  /*
   * antd renders `items[].icon` before the label; the shim dropped it, so all
   * four nested usage tabs lost the icons the reference shows.
   */
  test("nested usage tabs render their icons", async ({ page, app }) => {
    await app.goto("dashboard");
    const tab = page.getByRole("tab", { name: /Usage by Deployment/i });
    if ((await tab.count()) === 0) {
      test.skip(true, "usage tab not present");
    }
    await tab.click();
    await page.waitForLoadState("networkidle").catch(() => {});

    const nested = page.getByRole("tab", { name: /API Deployments/i });
    if ((await nested.count()) === 0) {
      test.skip(true, "nested tabs not present");
    }
    await expect(nested.locator("svg").first()).toBeVisible();
  });

  /*
   * react-day-picker renders ONE nav for the whole calendar. Anchoring the
   * absolute prev/next buttons to `.month` pinned both to the FIRST month, so
   * with two months visible the "next" arrow sat mid-popover.
   */
  test("the range picker puts its nav arrows at the calendar edges", async ({
    page,
    app,
  }) => {
    await app.goto("dashboard");
    const trigger = page.locator(".ant-picker").first();
    if ((await trigger.count()) === 0) {
      test.skip(true, "no range picker on this dashboard");
    }
    await trigger.click();

    const next = page.locator("[data-testid='next-month'], .rdp-button_next").first();
    await expect(next).toBeVisible({ timeout: 5000 });

    const placed = await next.evaluate((btn) => {
      const months = btn.closest("[class*='relative']")?.querySelector(".flex.flex-row");
      const row = months ?? btn.parentElement;
      const b = btn.getBoundingClientRect();
      const r = row.getBoundingClientRect();
      // "Next" belongs in the right-hand half of the whole calendar, not the
      // middle (which is where it landed when anchored to the first month).
      return b.left > r.left + r.width / 2;
    });
    expect(placed, "next-month arrow is not at the calendar's right edge").toBe(
      true,
    );
  });

  test("the subscription tab renders", async ({ page, app }) => {
    await app.goto("dashboard");
    const tab = page.getByRole("tab", { name: /Subscription/i });
    if ((await tab.count()) === 0) {
      test.skip(true, "subscription tab not present");
    }
    await tab.click();
    await expectNoHorizontalOverflow(page, "subscription tab");
  });
});
