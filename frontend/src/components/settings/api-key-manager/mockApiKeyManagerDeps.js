import { vi } from "vitest";

/**
 * Mock everything a screen built on `ApiKeyManager` reaches outside React:
 * the HTTP client, clipboard, exception handler, alert and session stores,
 * and navigation. The session belongs to org `org_test`.
 *
 * `vi.doMock` is not hoisted, so call this before dynamically importing the
 * screen under test:
 *
 *   const axiosPrivate = vi.fn(() => Promise.resolve({ data: [] }));
 *   mockApiKeyManagerDeps(axiosPrivate);
 *   const { AgentKvKeys } = await import("./AgentKvKeys.jsx");
 */
function mockApiKeyManagerDeps(axiosPrivate) {
  vi.doMock("../../../hooks/useAxiosPrivate", () => ({
    useAxiosPrivate: () => axiosPrivate,
  }));
  vi.doMock("../../../hooks/useCopyToClipboard", () => ({
    useCopyToClipboard: () => vi.fn(),
  }));
  vi.doMock("../../../hooks/useExceptionHandler.jsx", () => ({
    useExceptionHandler: () => (_err, fallback) => ({ content: fallback }),
  }));
  vi.doMock("../../../store/alert-store", () => ({
    useAlertStore: () => ({ setAlertDetails: vi.fn() }),
  }));
  vi.doMock("../../../store/session-store", () => ({
    useSessionStore: () => ({
      sessionDetails: { orgId: "org_test", orgName: "acme", csrfToken: "t" },
    }),
  }));
  vi.doMock("react-router-dom", async () => {
    const actual = await vi.importActual("react-router-dom");
    return { ...actual, useNavigate: () => vi.fn() };
  });
}

export { mockApiKeyManagerDeps };
