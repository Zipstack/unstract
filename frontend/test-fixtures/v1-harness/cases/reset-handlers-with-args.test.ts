import { HttpResponse, http, server } from "@v1/test";
import { expect, it } from "vitest";

// Known bad: resetHandlers with arguments must not disable the guard.
it("resets to its own handlers, then calls an unmocked URL", async () => {
  server.resetHandlers(http.get("/api/v1/known", () => HttpResponse.json({})));
  await (await fetch("/api/v1/known")).json();
  await expect(fetch("/api/v1/unstract/org-1/unknown/")).rejects.toThrow();
});
