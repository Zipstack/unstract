import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { registerA11yMatchers } from "./a11y";
import {
  server,
  takeUnhandledRequests,
  unhandledRequestsMessage,
} from "./network";
import { removePortalContainer } from "./providers";

/*
 * Runs before every v1 test file (vitest.v1.config.mts `setupFiles`).
 * `globals: false` means Testing Library cannot register its own cleanup, so
 * it is done here.
 */

registerA11yMatchers();

beforeAll(() => {
  // The catch-all handler in network.ts answers every unmocked HTTP request,
  // so this only fires for what it cannot match; fail loudly there too.
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  removePortalContainer();
  server.resetHandlers();
  // Thrown from afterEach so it fails the test even when the code under test
  // caught the network error.
  const unhandled = takeUnhandledRequests();
  if (unhandled.length > 0) {
    throw new Error(unhandledRequestsMessage(unhandled));
  }
});

afterAll(() => {
  server.close();
});
