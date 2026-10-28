import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Deployment and pipeline keys are credentials. Whatever the table renders is
 * also in the page text a browsing agent or a screen share picks up, so the
 * full key must not be in the DOM until someone asks to see it — and copying
 * it must not require that.
 */
vi.mock("../../../hooks/useAxiosPrivate", () => ({
  useAxiosPrivate: () => vi.fn(() => Promise.resolve({ data: {} })),
}));
vi.mock("../../../hooks/useExceptionHandler.jsx", () => ({
  useExceptionHandler: () => (_err, fallback) => ({ content: fallback }),
}));
vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails: vi.fn() }),
}));
vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: { orgId: "org_test", csrfToken: "t" },
  }),
}));

const { ManageKeys } = await import("./ManageKeys.jsx");

const FULL_KEY = "4f9c2a17-8e3b-4d6a-9b0c-1d2e3f4a7c91";
const KEYS = [
  { id: "key-1", description: "CI", api_key: FULL_KEY, is_active: true },
];

const renderKeys = (props = {}) =>
  render(
    <ManageKeys
      isDialogOpen
      setDialogOpen={vi.fn()}
      apiKeys={KEYS}
      setApiKeys={vi.fn()}
      selectedApiRow={{ id: "dep-1", is_owner: true }}
      apiService={{}}
      type="api"
      {...props}
    />,
  );

describe("ManageKeys key column", () => {
  let writeText;

  beforeEach(() => {
    writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  afterEach(() => {
    delete navigator.clipboard;
  });

  it("shows only the last four characters by default", async () => {
    renderKeys();

    expect(await screen.findByText("••••••••7c91")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(FULL_KEY);
  });

  it("copies the full key without revealing it", async () => {
    renderKeys();

    fireEvent.click(await screen.findByLabelText("Copy API key"));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(FULL_KEY));
    expect(document.body.innerHTML).not.toContain(FULL_KEY);
  });

  it("reveals the key on request and hides it again", async () => {
    renderKeys();

    fireEvent.click(await screen.findByLabelText("Show API key"));
    expect(screen.getByText(FULL_KEY)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Hide API key"));
    expect(document.body.innerHTML).not.toContain(FULL_KEY);
  });

  it("masks a revealed key again when the modal is reopened", async () => {
    const { rerender } = renderKeys();
    const rerenderOpen = (isDialogOpen) =>
      rerender(
        <ManageKeys
          isDialogOpen={isDialogOpen}
          setDialogOpen={vi.fn()}
          apiKeys={KEYS}
          setApiKeys={vi.fn()}
          selectedApiRow={{ id: "dep-1", is_owner: true }}
          apiService={{}}
          type="api"
        />,
      );

    fireEvent.click(await screen.findByLabelText("Show API key"));
    expect(screen.getByText(FULL_KEY)).toBeInTheDocument();

    rerenderOpen(false);
    rerenderOpen(true);

    expect(await screen.findByText("••••••••7c91")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(FULL_KEY);
  });
});
