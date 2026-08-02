import {
  expect,
  expectNoHorizontalOverflow,
  test,
} from "./fixtures.js";

/**
 * API Deployments, Logs, and Agentic Prompt Studio.
 */

test.describe("api deployments", () => {
  test("renders without horizontal overflow", async ({ page, app }) => {
    await app.goto("api");
    await expectNoHorizontalOverflow(page, "api deployments");
  });

  /*
   * The enabled/disabled toggle is a `<Switch>` inside a `<Tooltip>`. Radix's
   * TooltipTrigger merges its OWN `data-state` (the tooltip's open state) onto
   * the `asChild` child, flipping "checked" to "closed" — and because shadcn's
   * Switch styled off `data-state`, an ENABLED deployment rendered as an empty
   * grey pill with the knob on the left.
   *
   * Asserting the rendered geometry, not the attribute: the fix was to key the
   * style off `aria-checked` precisely because `data-state` is unreliable here.
   */
  test("an enabled toggle renders visibly on", async ({ page, app }) => {
    await app.goto("api");
    const sw = page.locator("[role=switch][aria-checked='true']").first();
    if ((await sw.count()) === 0) {
      test.skip(true, "no enabled deployment in this org");
    }

    const look = await sw.evaluate((el) => {
      const track = getComputedStyle(el);
      const thumb = el.firstElementChild;
      return {
        track: track.backgroundColor,
        // Tailwind v4 emits `translate`, not `transform` — reading only
        // `transform` here would report "none" on a correctly-shifted knob.
        translate: thumb ? getComputedStyle(thumb).translate : "",
      };
    });

    // A checked track must be painted, not transparent.
    expect(
      look.track,
      "checked switch track is transparent (renders as a blank pill)",
    ).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
    // And the knob must have moved off the left edge.
    expect(look.translate, "checked switch knob is not shifted right").not.toBe(
      "none",
    );
  });
});

test.describe("logs", () => {
  test("renders without horizontal overflow", async ({ page, app }) => {
    await app.goto("logs");
    await expectNoHorizontalOverflow(page, "logs");
  });

  /*
   * With `showTime` the RangePicker label carries full timestamps (~40 chars).
   * A `whitespace-nowrap` span with no min-width floor forced the trigger past
   * its container and the filter row broke apart as soon as a range was picked.
   */
  test("the filter row survives a picked date range", async ({ page, app }) => {
    await app.goto("logs");
    const picker = page.locator(".ant-picker").first();
    if ((await picker.count()) === 0) {
      test.skip(true, "no range picker on the logs page");
    }

    const fits = await picker.evaluate((el) => {
      const parent = el.parentElement;
      if (!parent) return true;
      return el.getBoundingClientRect().width <= parent.getBoundingClientRect().width + 1;
    });
    expect(fits, "the range picker is wider than its container").toBe(true);
    await expectNoHorizontalOverflow(page, "logs filter row");
  });
});

test.describe("agentic prompt studio", () => {
  /*
   * `.aps-projects-list-wrapper` is `height: 100%` with `padding-bottom: 40px`.
   * With the empty state there is nothing to scroll, but the padding still
   * pushed content past the container and drew a scrollbar over a page with no
   * overflow — 565px of content in a 520px box.
   */
  test("the projects list does not scroll when there is nothing to scroll", async ({
    page,
    app,
  }) => {
    await app.goto("agentic-prompt-studio/projects");
    const wrapper = page.locator("[class*='aps-projects-list-wrap']");
    if ((await wrapper.count()) === 0) {
      test.skip(true, "agentic prompt studio list not rendered");
    }

    const overflow = await wrapper.first().evaluate(
      (el) => el.scrollHeight - el.clientHeight,
    );
    // A populated list legitimately scrolls; only the empty state must not.
    const isEmpty = (await page.locator(".ant-list-empty-text").count()) > 0;
    if (!isEmpty) {
      test.skip(true, "list has projects; scrolling is expected");
    }
    expect(
      overflow,
      "empty projects list shows a scrollbar with nothing to scroll",
    ).toBeLessThanOrEqual(0);
  });
});
