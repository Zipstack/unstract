import { describe, expect, it } from "vitest";

import { getOrgSwitchLoginUrl, isOrgSwitchViaLogin } from "./orgSwitchLogin.js";

describe("isOrgSwitchViaLogin", () => {
  it("is true only for a literal true on the session", () => {
    expect(isOrgSwitchViaLogin({ org_switch_via_login: true })).toBe(true);
    for (const value of [undefined, false, "true", 1]) {
      expect(isOrgSwitchViaLogin({ org_switch_via_login: value })).toBe(false);
    }
    expect(isOrgSwitchViaLogin(undefined)).toBe(false);
  });
});

describe("getOrgSwitchLoginUrl", () => {
  it("logs in again silently, naming the organization", () => {
    const url = new URL(getOrgSwitchLoginUrl("org_b&x=1"));

    expect(url.origin).toBe(window.location.origin);
    expect(url.pathname).toBe("/api/v1/login");
    expect(url.searchParams.get("organization")).toBe("org_b&x=1");
    expect(url.searchParams.get("prompt")).toBe("none");
    expect([...url.searchParams.keys()]).toEqual(["organization", "prompt"]);
  });
});
