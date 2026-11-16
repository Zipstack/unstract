import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Copying an adapter's id, driven through the screen that is actually routed.
 *
 * This test exists because the first attempt at the feature did not. The Copy
 * ID action was added to `ListOfItems` — a card component that reads exactly
 * like the adapter list and is imported by NOTHING. `Settings → LLMs` renders
 * `ToolSettings`, which uses `ResourceTable`. A unit test that mounted
 * `ListOfItems` directly passed, mutation-checked and all, while the button
 * was unreachable in the product. Caught in review (Greptile P1 on #2317).
 *
 * So the assertion that matters is not "the widget calls its prop" but "the
 * routed screen puts the control on the page". Mount `ToolSettings`.
 */
const copyToClipboard = vi.fn();
const ADAPTER = {
  id: "ff3f12e5-f119-44cb-9ecb-f35f16f87cbf",
  adapter_id: "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203",
  adapter_name: "sonnet 4.6",
  adapter_type: "LLM",
  description: "",
  created_at: "2026-10-01T00:00:00Z",
  modified_at: "2026-10-01T00:00:00Z",
  created_by_email: "owner@example.com",
  shared_users: [],
};

vi.mock("../../../hooks/useCopyToClipboard", () => ({
  useCopyToClipboard: () => copyToClipboard,
}));
vi.mock("../../../hooks/useAxiosPrivate", () => ({
  useAxiosPrivate: () => () => Promise.resolve({ data: [ADAPTER] }),
}));
vi.mock("../../../hooks/useExceptionHandler", () => ({
  useExceptionHandler: () => (_e, fallback) => ({ content: fallback }),
}));
vi.mock("../../../hooks/usePostHogEvents", () => ({
  default: () => ({ setPostHogCustomEvent: () => undefined }),
}));
// `CoOwnerModal` renders unconditionally and dereferences
// `coOwner.coOwnerData.coOwners`, so the shape matters even though the modal
// is shut.
vi.mock("../../../hooks/useCoOwnerManagement", () => ({
  useCoOwnerManagement: () => ({
    handleCoOwner: vi.fn(),
    isCoOwnerModalOpen: false,
    closeCoOwnerModal: vi.fn(),
    coOwnerData: { coOwners: [], createdBy: null },
    coOwnerAllUsers: [],
    coOwnerLoading: false,
    setCoOwnerModalOpen: vi.fn(),
  }),
}));
vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails: vi.fn() }),
}));
vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: {
      orgId: "org_test",
      orgName: "acme",
      email: "owner@example.com",
    },
  }),
}));
vi.mock("../../groups/groups-service.js", () => ({
  groupsService: () => ({ getGroups: () => Promise.resolve({ data: [] }) }),
}));

const { ToolSettings } = await import("./ToolSettings.jsx");

describe("ToolSettings — Copy ID", () => {
  beforeEach(() => {
    copyToClipboard.mockClear();
  });

  it("puts a Copy ID control on the adapter row", async () => {
    render(
      <MemoryRouter>
        <ToolSettings type="llm" />
      </MemoryRouter>,
    );

    const button = await screen.findByLabelText("Copy Adapter ID");
    fireEvent.click(button);

    await waitFor(() => expect(copyToClipboard).toHaveBeenCalled());
  });

  it("copies the instance id, not the provider descriptor", async () => {
    render(
      <MemoryRouter>
        <ToolSettings type="llm" />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByLabelText("Copy Adapter ID"));

    await waitFor(() => expect(copyToClipboard).toHaveBeenCalled());
    const [value] = copyToClipboard.mock.calls[0];
    expect(value).toBe(ADAPTER.id);
    expect(value).not.toBe(ADAPTER.adapter_id);
  });
});
