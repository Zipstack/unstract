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
function serveBackend() {
  axios.mockImplementation(({ method, url }) => {
    calledUrls.push(url);
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

async function validateSession(session) {
  sessionData.mockResolvedValue(session);
  serveBackend();
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
});
