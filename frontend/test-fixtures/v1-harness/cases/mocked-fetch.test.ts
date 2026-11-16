import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
} from "@v1/test";
import { expect, it } from "vitest";

// Known good: the same request with a handler passes.
it("loads adapters with a handler", async () => {
  const url = apiPath(DEFAULT_SESSION, "/adapter/");
  mockApi(http.get(url, () => HttpResponse.json([{ id: "a1" }])));
  const response = await fetch(url);
  expect(await response.json()).toEqual([{ id: "a1" }]);
});
