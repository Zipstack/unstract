import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * "Export as Tool" first loads the org's users. When that load fails the
 * failure is already reported, and the export must stop there rather than
 * read `users.length` off `undefined`.
 */
const setAlertDetails = vi.fn();
const axiosPrivate = vi.fn(() => Promise.reject(new Error("users down")));

vi.mock("../../../hooks/useAxiosPrivate", () => ({
  useAxiosPrivate: () => axiosPrivate,
}));
vi.mock("../../../hooks/useExceptionHandler", () => ({
  useExceptionHandler: () => (_err, fallback) => ({
    type: "error",
    content: fallback,
  }),
}));
vi.mock("../../../hooks/usePostHogEvents", () => ({
  default: () => ({ setPostHogCustomEvent: vi.fn() }),
}));
vi.mock("../../../hooks/usePromptStudioCanEdit", () => ({
  usePromptStudioCanEdit: () => true,
}));
vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails }),
}));
vi.mock("../../../store/custom-tool-store", () => ({
  useCustomToolStore: () => ({
    details: { tool_id: "tool-1", tool_name: "Tool", created_by: 7 },
    isPublicSource: false,
    markChangesAsExported: vi.fn(),
  }),
}));
vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: { orgId: "org_test", orgName: "acme", csrfToken: "t" },
  }),
}));
vi.mock("../../navigations/tool-nav-bar/ToolNavBar", () => ({
  ToolNavBar: ({ customButtons }) => <div>{customButtons}</div>,
}));
vi.mock("../export-tool/ExportTool", () => ({ ExportTool: () => null }));
vi.mock(
  "../../deployments/create-api-deployment-from-prompt-studio/CreateApiDeploymentFromPromptStudio.jsx",
  () => ({ CreateApiDeploymentFromPromptStudio: () => null }),
);
vi.mock("@/components/ui/shims/antd-overlays", async () => {
  const actual = await vi.importActual("@/components/ui/shims/antd-overlays");
  return {
    ...actual,
    Dropdown: ({ menu, children }) => (
      <div>
        {children}
        {menu.items.map((item) => (
          <button key={item.key} type="button" onClick={item.onClick}>
            {item.label}
          </button>
        ))}
      </div>
    ),
  };
});

const { Header } = await import("./Header.jsx");

describe("Header export as tool", () => {
  it("stops after a failed users load without throwing", async () => {
    render(
      <Header
        setOpenSettings={vi.fn()}
        handleUpdateTool={vi.fn()}
        setOpenShareModal={vi.fn()}
        setOpenCloneModal={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Export as Tool"));

    await waitFor(() =>
      expect(setAlertDetails).toHaveBeenCalledWith({
        type: "error",
        content: "Failed to load",
      }),
    );
    // Let the export handler's `.then` run on the failed load.
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(axiosPrivate).toHaveBeenCalledTimes(1);
    expect(axiosPrivate.mock.calls[0][0].url).toBe(
      "/api/v1/unstract/org_test/users/",
    );
  });
});
