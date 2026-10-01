import { afterEach, describe, expect, it } from "vitest";

import { useSessionStore } from "../store/session-store";
import { orgApi } from "./orgApi";

describe("orgApi", () => {
  afterEach(() => {
    useSessionStore.setState({ sessionDetails: {} });
  });

  it("prefixes the path with the signed-in org", () => {
    useSessionStore.setState({ sessionDetails: { orgId: "org-1" } });
    expect(orgApi("items/")).toBe("/api/v1/unstract/org-1/items/");
  });

  it("tolerates a leading slash", () => {
    useSessionStore.setState({ sessionDetails: { orgId: "org-1" } });
    expect(orgApi("/items/42/")).toBe("/api/v1/unstract/org-1/items/42/");
  });

  it("reads the org at call time", () => {
    useSessionStore.setState({ sessionDetails: { orgId: "org-1" } });
    useSessionStore.setState({ sessionDetails: { orgId: "org-2" } });
    expect(orgApi("items/")).toBe("/api/v1/unstract/org-2/items/");
  });
});
