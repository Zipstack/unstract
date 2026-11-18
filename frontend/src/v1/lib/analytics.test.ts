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
  makeSession({ organization: { id: "org_abc", name: "Acme" } }),
);
const oss = toV1Session(
  makeSession({ organization: { id: "mock_org", name: "Mock" } }),
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

  it("identifies by email, with the name, only on Unstract's SaaS", () => {
    onHost("us-central.unstract.com");
    identifyUser(cloud);
    expect(posthog.identify).toHaveBeenCalledWith("ada@example.com", {
      org: "org_abc",
      software: "SAAS",
      userId: "1",
      name: "Ada",
      email: "ada@example.com",
    });
    expect(posthog.register).toHaveBeenCalledWith({
      org_id: "org_abc",
      org_name: "org_abc",
      software: "SAAS",
    });
  });

  it.each([
    ["a self-hosted install", "unstract.example.com", cloud, "SAAS"],
    ["OSS, even on a SaaS host", "us-central.unstract.com", oss, "OSS"],
  ])("identifies %s anonymously, by organisation and user id", (_, host, session, software) => {
    onHost(host);
    identifyUser(session);
    expect(posthog.identify).toHaveBeenCalledWith(
      `${session.organization.id}:1`,
      { org: session.organization.name, software, userId: "1" },
    );
  });

  it("does nothing where PostHog is not started", () => {
    posthog.__loaded = false;
    registerUiVersion("v0");
    identifyUser(cloud);
    expect(posthog.register).not.toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });
});
