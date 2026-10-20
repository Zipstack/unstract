/**
 * Drives one screen through rest, loading, empty, error and no-permission by
 * intercepting the API call it loads from, and asserts each state rendered.
 *
 *   await expectFiveStates(page, {
 *     open: () => app.goto("workflows"),
 *     api: "**\/api/v1/unstract/*\/workflow/?*",
 *     rest: (p) => p.getByRole("table"),
 *     emptyBody: { results: [] },
 *   });
 *
 * - rest: the real response, or `restBody` when the screen is stubbed.
 * - loading: the response is held; the skeleton must show while it is, then
 *   the response is released and rest must follow.
 * - empty: `emptyBody` with 200. error: a 500. no-permission: a 403. The
 *   no-permission state comes from interception, not from a real low-role
 *   user, so it needs no extra credentials.
 *
 * A held response is always released in `finally`, so a failed assertion
 * cannot leave the page waiting on it until the test timeout.
 */

import {
  expect,
  type Locator,
  type Page,
  type Route,
  test,
} from "@playwright/test";
import { STATE_TEST_IDS } from "../contract/v1-ui.ts";

export type ScreenState =
  | "rest"
  | "loading"
  | "empty"
  | "error"
  | "noPermission";

export const ALL_STATES: readonly ScreenState[] = [
  "rest",
  "loading",
  "empty",
  "error",
  "noPermission",
];

type StateLocator = (page: Page) => Locator;

export interface Screen {
  /** Navigates to the screen; called once per state. */
  open: () => Promise<unknown>;
  /** URL glob or regex of the API call the screen renders from. */
  api: string | RegExp;
  /** What proves the screen is at rest with data. */
  rest: StateLocator;
  /** Body the empty state is driven with (the API's empty shape). */
  emptyBody: unknown;
  /** Stubs rest too, for a screen whose API is not real. */
  restBody?: unknown;
  /** Overrides for the core state components' default test ids. */
  locators?: Partial<Record<Exclude<ScreenState, "rest">, StateLocator>>;
  /** Subset to drive, where a state does not apply. Default: all five. */
  states?: readonly ScreenState[];
  /** Per-state wait. Default: the expect timeout. */
  timeout?: number;
}

function defaultLocator(state: Exclude<ScreenState, "rest">): StateLocator {
  return (page) => page.getByTestId(STATE_TEST_IDS[state]);
}

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/**
 * Hands the request on (to an earlier handler, else the real API), or fulfils
 * the stubbed rest body. `fallback`, not `continue`: `continue` would skip any
 * route the spec itself installed.
 */
function passThrough(screen: Screen) {
  return (route: Route) =>
    screen.restBody === undefined
      ? route.fallback()
      : json(route, 200, screen.restBody);
}

const STATUS_BODIES = {
  error: { status: 500, body: { detail: "e2e: forced server error" } },
  noPermission: { status: 403, body: { detail: "e2e: forced 403" } },
} as const;

async function withRoute(
  page: Page,
  screen: Screen,
  handler: (route: Route) => Promise<void>,
  body: () => Promise<void>,
): Promise<void> {
  await page.route(screen.api, handler);
  try {
    await body();
  } finally {
    await page.unroute(screen.api, handler);
  }
}

async function driveState(
  page: Page,
  screen: Screen,
  state: ScreenState,
): Promise<void> {
  const timeout = screen.timeout;
  const locatorFor = (s: Exclude<ScreenState, "rest">) =>
    (screen.locators?.[s] ?? defaultLocator(s))(page);

  switch (state) {
    case "rest":
      await withRoute(page, screen, passThrough(screen), async () => {
        await screen.open();
        await expect(screen.rest(page)).toBeVisible({ timeout });
      });
      return;

    case "loading": {
      let release: () => void = () => {};
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const rest = passThrough(screen);
      const hold = async (route: Route) => {
        await gate;
        // The page may have navigated away after a failure; nothing to answer.
        await rest(route).catch(() => null);
      };
      await withRoute(page, screen, hold, async () => {
        /*
         * Not awaited until the response is released: `open` may wait for
         * networkidle (`app.goto` does), which cannot happen while the
         * response is held. Settled into a value so it cannot reject unseen.
         */
        const opened = screen.open().then(
          () => null,
          (err: unknown) => err,
        );
        try {
          await expect(locatorFor("loading")).toBeVisible({ timeout });
          await expect(screen.rest(page)).toBeHidden({ timeout });
        } finally {
          release();
        }
        const openError = await opened;
        if (openError) {
          throw openError;
        }
        await expect(screen.rest(page)).toBeVisible({ timeout });
        await expect(locatorFor("loading")).toBeHidden({ timeout });
      });
      return;
    }

    case "empty":
      await withRoute(
        page,
        screen,
        (route) => json(route, 200, screen.emptyBody),
        async () => {
          await screen.open();
          await expect(locatorFor("empty")).toBeVisible({ timeout });
        },
      );
      return;

    case "error":
    case "noPermission": {
      const { status, body } = STATUS_BODIES[state];
      await withRoute(
        page,
        screen,
        (route) => json(route, status, body),
        async () => {
          await screen.open();
          await expect(locatorFor(state)).toBeVisible({ timeout });
        },
      );
      return;
    }
  }
}

export async function expectFiveStates(
  page: Page,
  screen: Screen,
): Promise<void> {
  for (const state of screen.states ?? ALL_STATES) {
    await test.step(`state: ${state}`, () => driveState(page, screen, state));
  }
}
