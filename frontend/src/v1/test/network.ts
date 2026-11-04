import {
  HttpResponse,
  http,
  type RequestHandler,
  type WebSocketHandler,
  ws,
} from "msw";
import { setupServer } from "msw/node";
import type { TestSession } from "./session";

/*
 * Network mocking at the HTTP boundary. MSW intercepts fetch, XHR (so axios
 * too) and WebSocket. setup.ts starts the server, resets handlers after each
 * test, and fails the test if any request went unmocked.
 */

export { delay, HttpResponse, http, ws } from "msw";

const unhandledRequests: string[] = [];

/*
 * Unmocked requests are answered by catch-all handlers, not by MSW's
 * `onUnhandledRequest: "error"`. Under happy-dom that strategy does not stop
 * an HTTP request: happy-dom's fetch falls through to Node's http, which MSW
 * intercepts a second time, and then the request really goes out. For a
 * WebSocket it only logs, and the mocked socket opens. A handler that
 * returns a network error, or closes the socket, ends it in-process.
 */
const unmockedSocketHandler: WebSocketHandler = ws
  .link(/.*/)
  .addEventListener("connection", ({ client }) => {
    // MSW runs EVERY matching WebSocket handler (HTTP stops at the first), so
    // step aside when a test's own ws.link() handles this URL.
    const mocked = server
      .listHandlers()
      .some(
        (handler) =>
          handler !== unmockedSocketHandler &&
          handler.kind === "websocket" &&
          handler.test(client.url),
      );
    if (mocked) {
      return;
    }
    unhandledRequests.push(`WEBSOCKET ${client.url.href}`);
    client.close(1011, "Unmocked WebSocket");
  });

const unmockedHandlers: (RequestHandler | WebSocketHandler)[] = [
  http.all("*", ({ request }) => {
    unhandledRequests.push(`${request.method} ${request.url}`);
    return HttpResponse.error();
  }),
  unmockedSocketHandler,
];

export const server = setupServer(...unmockedHandlers);

/*
 * server.use() prepends, so the catch-alls always match last. resetHandlers
 * with arguments would replace them, so it is pinned to re-append them.
 */
const resetHandlers = server.resetHandlers.bind(server);
server.resetHandlers = (...handlers) =>
  resetHandlers(...handlers, ...unmockedHandlers);

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
