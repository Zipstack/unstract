import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import type { TestSession } from "./session";

/*
 * Network mocking at the HTTP boundary. MSW intercepts fetch and XHR (so
 * axios too). setup.ts starts the server, resets handlers after each test,
 * and fails the test if any request went unmocked.
 */

export { delay, HttpResponse, http } from "msw";

const unhandledRequests: string[] = [];

/*
 * Unmocked requests are answered by a catch-all handler, not by MSW's
 * `onUnhandledRequest: "error"`. Under happy-dom that strategy does not stop
 * the request: happy-dom's fetch falls through to Node's http, which MSW
 * intercepts a second time, and then the request really goes out. A handler
 * that returns a network error ends it at the first interception. Handlers
 * added with server.use() are prepended, so this one always matches last,
 * and resetHandlers() keeps it.
 */
const unmockedRequestHandler = http.all("*", ({ request }) => {
  unhandledRequests.push(`${request.method} ${request.url}`);
  return HttpResponse.error();
});

export const server = setupServer(unmockedRequestHandler);

/** Returns and clears the requests no handler matched since the last call. */
export function takeUnhandledRequests(): string[] {
  return unhandledRequests.splice(0);
}

/** The message a test fails with when it made unmocked requests. */
export function unhandledRequestsMessage(requests: readonly string[]): string {
  return [
    `Unmocked request${requests.length === 1 ? "" : "s"} (add a handler with mockApi() or server.use()):`,
    ...requests.map((request) => `  ${request}`),
  ].join("\n");
}

/** Adds handlers for the current test only; they are reset after it. */
export const mockApi: typeof server.use = (...handlers) =>
  server.use(...handlers);

/** v0's org-scoped API prefix, `/api/v1/unstract/<org id>`. */
export function apiPath(session: TestSession, path: `/${string}`): string {
  return `/api/v1/unstract/${session.organization.id}${path}`;
}
