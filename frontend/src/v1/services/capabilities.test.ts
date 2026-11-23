import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
} from "@v1/test";
import { afterEach, beforeEach, expect, it } from "vitest";
import { capabilityQueries, listCapabilities } from "./capabilities";
import { setOrganizationId } from "./context";

const URL = apiPath(DEFAULT_SESSION, "/organization/capabilities/");

beforeEach(() => setOrganizationId(DEFAULT_SESSION.organization.id));
afterEach(() => setOrganizationId(null));

it("lists the capabilities in the current organisation, keyed by it", async () => {
  const capabilities = [{ key: "create_connectors", allowed_for_me: true }];
  mockApi(http.get(URL, () => HttpResponse.json({ capabilities })));
  expect(await listCapabilities()).toEqual(capabilities);
  expect(capabilityQueries.list().queryKey).toEqual([
    DEFAULT_SESSION.organization.id,
    "capabilities",
  ]);
});

it("rejects a reply that carries no capabilities", async () => {
  mockApi(http.get(URL, () => HttpResponse.json({ html: true })));
  await expect(listCapabilities()).rejects.toThrow(/carried no capabilities/);
});
