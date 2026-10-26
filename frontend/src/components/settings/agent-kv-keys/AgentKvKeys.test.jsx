import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Which keys this screen manages.
 *
 * `AgentKvKeys` is a thin wrapper over the shared `ApiKeyManager`, and every
 * request it makes is built from one prop: `resourcePath`. A copy of
 * `PlatformApiKeys` that forgot to change that prop renders an identical,
 * entirely plausible screen — titled "Agent-KV API Keys", reached from the
 * Agent-KV nav entry — while creating, rotating and DELETING platform API
 * keys. Nothing visible distinguishes the two, so the URL is the assertion.
 */
const axiosPrivate = vi.fn(() => Promise.resolve({ data: [] }));

vi.mock("../../../hooks/useAxiosPrivate", () => ({
  useAxiosPrivate: () => axiosPrivate,
}));
vi.mock("../../../hooks/useCopyToClipboard", () => ({
  useCopyToClipboard: () => vi.fn(),
}));
vi.mock("../../../hooks/useExceptionHandler.jsx", () => ({
  useExceptionHandler: () => (_err, fallback) => ({ content: fallback }),
}));
vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails: vi.fn() }),
}));
vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: { orgId: "org_test", orgName: "acme", csrfToken: "t" },
  }),
}));
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

const { AgentKvKeys } = await import("./AgentKvKeys.jsx");

describe("AgentKvKeys", () => {
  beforeEach(() => {
    axiosPrivate.mockClear();
  });

  it("reads keys from the agent-kv resource, not the platform one", async () => {
    render(<AgentKvKeys />);

    await waitFor(() => expect(axiosPrivate).toHaveBeenCalled());

    const urls = axiosPrivate.mock.calls.map(([args]) => args?.url);
    expect(urls).toContain("/api/v1/unstract/org_test/agent-kv/keys/");
    expect(urls.join(" ")).not.toContain("platform-api");
  });

  it("is titled for the API the key is used against", async () => {
    render(<AgentKvKeys />);

    expect(await screen.findByText("Agent-KV API Keys")).toBeInTheDocument();
  });
});
