import { renderHook } from "@testing-library/react";
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../store/session-store";

vi.mock("axios");

const navigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => navigate,
}));

const sessionData = vi.fn();
vi.mock("./useUserSession.js", () => ({
  useUserSession: () => sessionData,
}));

vi.mock("../helpers/FeatureFlagsData.js", () => ({
  listFlags: vi.fn().mockResolvedValue({}),
}));

const { default: useSessionValid } = await import("./useSessionValid.js");

const ORGS = [
  { id: "org-a", display_name: "Org A" },
  { id: "org-b", display_name: "Org B" },
];

// The backend's answers, by URL; anything else would be an unexpected call.
// `fail` maps a URL suffix to the error that call rejects with.
function serveBackend(fail = {}) {
  axios.mockImplementation(({ method, url }) => {
    calledUrls.push(url);
    const failure = Object.keys(fail).find((suffix) => url.endsWith(suffix));
    if (failure) {
      return Promise.reject(fail[failure]);
    }
    if (url === "/api/v1/organization") {
      return Promise.resolve({ data: { organizations: ORGS } });
    }
    const set = url.match(/^\/api\/v1\/organization\/([^/]+)\/set$/);
    if (method === "POST" && set) {
      return Promise.resolve({
        data: { user: { name: "U" }, organization: { name: set[1] } },
      });
    }
    if (url.endsWith("/users/profile/")) {
      return Promise.resolve({ data: { user: { is_admin: false } } });
    }
    if (url.endsWith("/adapter/")) {
      return Promise.resolve({ data: [] });
    }
    return Promise.reject(new Error(`unexpected ${method} ${url}`));
  });
}

async function validateSession(session, fail) {
  sessionData.mockResolvedValue(session);
  serveBackend(fail);
  const { result } = renderHook(() => useSessionValid());
  await result.current();
  return useSessionStore.getState().sessionDetails;
}

// The hook reuses one options object across calls, so match on the URL each
// call was made with, captured at call time.
const calledUrls = [];

function setOrgUrls() {
  return calledUrls.filter((url) => url.endsWith("/set"));
}

// What the org-scoped APIs answer once the organization's trial has ended.
function trialExpired() {
  const err = new Error("Request failed with status code 403");
  err.response = { status: 403, data: { detail: "Trial period expired" } };
  return err;
}

afterEach(() => {
  vi.clearAllMocks();
  calledUrls.length = 0;
  useSessionStore.setState({ sessionDetails: {} });
});

describe("useSessionValid", () => {
  it("asks a multi-organization user to pick when the session has none", async () => {
    await validateSession({ organization_id: null });

    expect(navigate).toHaveBeenCalledWith("/setOrg", { state: ORGS });
    expect(setOrgUrls()).toEqual([]);
  });

  it("skips the picker and keeps the organization the login entered", async () => {
    const details = await validateSession({
      organization_id: "org-b",
      org_switch_via_login: true,
    });

    expect(navigate).not.toHaveBeenCalledWith("/setOrg", expect.anything());
    expect(setOrgUrls()).toEqual(["/api/v1/organization/org-b/set"]);
    expect(details.orgId).toBe("org-b");
    expect(details.orgSwitchViaLogin).toBe(true);
  });

  it("leaves the flag off for a session without it", async () => {
    const details = await validateSession({ organization_id: "org-a" });

    expect(setOrgUrls()).toEqual(["/api/v1/organization/org-a/set"]);
    expect(details.orgSwitchViaLogin).toBe(false);
  });

  it.each([
    ["the profile", "/users/profile/"],
    ["the adapters", "/adapter/"],
  ])("keeps the organizations when %s call is refused", async (_label, suffix) => {
    const details = await validateSession(
      { organization_id: "org-a", org_switch_via_login: true, role: "admin" },
      { [suffix]: trialExpired() },
    );

    expect(details.isLoggedIn).toBe(true);
    expect(details.orgId).toBe("org-a");
    expect(details.allOrganization).toEqual(ORGS);
    expect(details.orgSwitchViaLogin).toBe(true);
    expect(details.role).toBe("admin");
  });

  it("keeps the organizations when the feature flags call is refused", async () => {
    const { listFlags } = await import("../helpers/FeatureFlagsData.js");
    listFlags.mockRejectedValueOnce(trialExpired());

    const details = await validateSession({
      organization_id: "org-a",
      org_switch_via_login: true,
    });

    expect(details.allOrganization).toEqual(ORGS);
    expect(details.orgSwitchViaLogin).toBe(true);
  });

  it("ends signed out when setting the organization fails", async () => {
    const details = await validateSession(
      { organization_id: "org-a" },
      { "/set": new Error("Network Error") },
    );

    expect(details).toEqual({ isLoggedIn: false });
  });
});
