import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The deployment scope on the create form (UN-4630).
 *
 * The picker is required only while "Allow all API deployments" is unchecked.
 * Toggling a `required` rule on and off per render does not work on the Form
 * shim: react-hook-form keeps the rules a field first registered with, so the
 * picker stayed required and an "Allow all" key could not be created.
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

const { GlobalApiDeploymentKeys } = await import(
  "./GlobalApiDeploymentKeys.jsx"
);

const KEYS_URL = "/api/v1/unstract/org_test/global-api-deployment/keys/";

const createCalls = () =>
  axiosPrivate.mock.calls
    .map(([args]) => args)
    .filter((args) => args?.method === "POST" && args?.url === KEYS_URL);

async function openCreateForm(user) {
  render(<GlobalApiDeploymentKeys />);
  await user.click(await screen.findByRole("button", { name: /new key/i }));
  await user.type(screen.getByPlaceholderText("Enter key name"), "Doe's key");
  await user.type(screen.getByPlaceholderText("Enter description"), "desc");
}

describe("GlobalApiDeploymentKeys create form", () => {
  beforeEach(() => {
    axiosPrivate.mockClear();
  });

  it("creates an 'Allow all' key without picking a deployment", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(
      screen.getByRole("checkbox", { name: /allow all api deployments/i }),
    );
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(createCalls()).toHaveLength(1));
    expect(createCalls()[0].data).toMatchObject({
      allow_all_deployments: true,
      api_deployments: [],
    });
    expect(
      screen.queryByText("Select at least one deployment"),
    ).not.toBeInTheDocument();
  });

  it("clears the picker's error once 'Allow all' is ticked", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(
      await screen.findByText("Select at least one deployment"),
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("checkbox", { name: /allow all api deployments/i }),
    );
    await waitFor(() =>
      expect(
        screen.queryByText("Select at least one deployment"),
      ).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(createCalls()).toHaveLength(1));
  });

  it("still requires a deployment when 'Allow all' is unchecked", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(
      await screen.findByText("Select at least one deployment"),
    ).toBeInTheDocument();
    expect(createCalls()).toHaveLength(0);
  });
});
