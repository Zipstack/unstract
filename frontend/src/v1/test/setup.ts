import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { registerA11yMatchers } from "./a11y";
import {
  server,
  takeUnhandledRequests,
  unhandledRequestsMessage,
} from "./network";
import { resetProviders } from "./providers";

/*
 * Runs before every v1 test file (vitest.v1.config.mts `setupFiles`).
 * `globals: false` means Testing Library cannot register its own cleanup, so
 * it is done here.
 */

registerA11yMatchers();

beforeAll(() => {
  // The catch-all handlers in network.ts answer every unmocked HTTP request
  // and WebSocket, so this only fires for what they cannot match.
  server.listen({ onUnhandledRequest: "error" });
});

/** Lets requests already started (e.g. by an unmount effect) reach MSW. */
async function settle(): Promise<void> {
  // A test that left fake timers on would stall the wait below forever.
  if (vi.isFakeTimers()) {
    vi.useRealTimers();
  }
  // Two macrotask turns, one after the other; the unmount cases in
  // test-fixtures/v1-harness fail if this stops being enough.
  await nextTurn();
  await nextTurn();
}

function nextTurn(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function failOnUnhandledRequests(): void {
  const unhandled = takeUnhandledRequests();
  if (unhandled.length > 0) {
    throw new Error(unhandledRequestsMessage(unhandled));
  }
}

afterEach(async () => {
  // Unmount first: cleanup effects may make requests, which belong to this
  // test and must still see its handlers.
  cleanup();
  resetProviders();
  await settle();
  server.resetHandlers();
  // Thrown from afterEach so it fails the test even when the code under test
  // caught the network error.
  failOnUnhandledRequests();
});

afterAll(async () => {
  // Requests made after the last test's afterEach (a timer firing during the
  // file's own afterAll) fail the file rather than vanish.
  await settle();
  try {
    failOnUnhandledRequests();
  } finally {
    server.close();
  }
});
