import { makeSession, toV1Session } from "@v1/test";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { identifyUser, registerUiVersion } from "./analytics";

const posthog = vi.hoisted(() => ({
  __loaded: true,
  identify: vi.fn(),
  register: vi.fn(),
}));
vi.mock("posthog-js", () => ({ default: posthog }));

const cloud = toV1Session(
  makeSession({
    organization: { id: "org_abc", name: "Acme", urlName: "acme" },
  }),
);
const oss = toV1Session(
  makeSession({
    organization: { id: "mock_org", name: "Mock", urlName: "mock_org" },
  }),
);

function onHost(hostname: string) {
  vi.stubGlobal("location", { ...window.location, hostname });
}

beforeEach(() => {
  posthog.__loaded = true;
  posthog.identify.mockReset();
  posthog.register.mockReset();
});

describe("analytics", () => {
  it("tags events with the version on screen", () => {
    registerUiVersion("v1");
    expect(posthog.register).toHaveBeenCalledWith({ ui_version: "v1" });
  });

  it.each([
    "us-central.unstract.com",
    "eu-west.unstract.com",
  ])("on SaaS (%s) identifies by email, leaving the name to v0", (host) => {
    onHost(host);
    identifyUser(cloud);
    expect(posthog.identify).toHaveBeenCalledWith("ada@example.com", {
      org: "acme",
      software: "SAAS",
      userId: 1,
      email: "ada@example.com",
    });
    expect(posthog.register).toHaveBeenCalledWith({
      org_id: "org_abc",
      org_name: "acme",
      software: "SAAS",
    });
  });

  it.each([
    ["a self-hosted install", "unstract.example.com", cloud, "SAAS"],
    ["OSS, even on a SaaS host", "us-central.unstract.com", oss, "OSS"],
  ])("identifies %s anonymously, by organisation id and user id", (_, host, session, software) => {
    onHost(host);
    identifyUser(session);
    expect(posthog.identify).toHaveBeenCalledWith(
      `${session.organization.id}:1`,
      { org: session.organization.name, software, userId: 1 },
    );
  });

  it("identifies a SaaS user with no email by the org-scoped id, never an empty one", () => {
    onHost("us-central.unstract.com");
    identifyUser({ ...cloud, user: { ...cloud.user, email: "" } });
    expect(posthog.identify).toHaveBeenCalledWith("org_abc:1", {
      org: "acme",
      software: "SAAS",
      userId: 1,
    });
  });

  it("does nothing where PostHog is not started", () => {
    posthog.__loaded = false;
    registerUiVersion("v0");
    identifyUser(cloud);
    expect(posthog.register).not.toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });

  it.each([
    ["register", () => registerUiVersion("v1")],
    ["identify", () => identifyUser(cloud)],
  ] as const)("only logs a failing %s, so analytics never breaks a page", (method, call) => {
    const logged = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const broke = new Error("posthog broke");
    posthog[method].mockImplementation(() => {
      throw broke;
    });
    expect(call).not.toThrow();
    expect(logged).toHaveBeenCalledTimes(1);
    expect(logged).toHaveBeenCalledWith(
      `[v1 analytics] ${method} failed`,
      broke,
    );
  });
});
