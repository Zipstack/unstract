import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The deployment scope on the create and edit forms (UN-4630).
 *
 * The picker is required only while "Allow all API deployments" is unchecked.
 * Toggling a `required` rule on and off per render does not work on the Form
 * shim: react-hook-form merges each render's rules into the field's
 * registration and never drops a key, so a `required` added while the box was
 * unchecked survived ticking it and blocked every "Allow all" save.
 */
const KEYS_URL = "/api/v1/unstract/org_test/global-api-deployment/keys/";
const DEPLOYMENTS_URL =
  "/api/v1/unstract/org_test/global-api-deployment/deployments/";
const SCOPE_ERROR = "Select at least one deployment";

const KEYS = [
  {
    id: "k_all",
    name: "AllKey",
    description: "all",
    key: "****-0001",
    is_active: true,
    allow_all_deployments: true,
    api_deployments: [],
  },
  {
    id: "k_scoped",
    name: "ScopedKey",
    description: "scoped",
    key: "****-0002",
    is_active: true,
    allow_all_deployments: false,
    api_deployments: [{ id: "d1", display_name: "Dep One" }],
  },
];

const axiosPrivate = vi.fn((args) => {
  if (args?.method === "GET" && args?.url === DEPLOYMENTS_URL) {
    return Promise.resolve({
      data: [
        { id: "d1", display_name: "Dep One", is_active: true },
        { id: "d2", display_name: "Dep Two", is_active: true },
      ],
    });
  }
  if (args?.method === "GET" && args?.url === KEYS_URL) {
    return Promise.resolve({ data: KEYS });
  }
  return Promise.resolve({ data: {} });
});

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

const writes = (method) =>
  axiosPrivate.mock.calls
    .map(([args]) => args)
    .filter((args) => args?.method === method);

const allowAllBox = () =>
  screen.getByRole("checkbox", { name: /allow all api deployments/i });

async function openCreateForm(user) {
  render(<GlobalApiDeploymentKeys />);
  await user.click(await screen.findByRole("button", { name: /new key/i }));
  await user.type(screen.getByPlaceholderText("Enter key name"), "Doe's key");
  await user.type(screen.getByPlaceholderText("Enter description"), "desc");
}

async function openEditForm(user, keyName) {
  render(<GlobalApiDeploymentKeys />);
  const row = (await screen.findByText(keyName)).closest("tr");
  // The row's icon-only actions have no accessible name; the pencil marks Edit.
  const edit = within(row)
    .getAllByRole("button")
    .find((button) => button.querySelector(".lucide-pencil"));
  await user.click(edit);
  await screen.findByRole("button", { name: "Save" });
}

describe("GlobalApiDeploymentKeys create form", () => {
  beforeEach(() => {
    axiosPrivate.mockClear();
  });

  it("creates an 'Allow all' key without picking a deployment", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(allowAllBox());
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(writes("POST")).toHaveLength(1));
    expect(writes("POST")[0]).toMatchObject({
      url: KEYS_URL,
      data: { allow_all_deployments: true, api_deployments: [] },
    });
  });

  it("clears the picker's error once 'Allow all' is ticked", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText(SCOPE_ERROR)).toBeInTheDocument();

    await user.click(allowAllBox());
    await waitFor(() =>
      expect(screen.queryByText(SCOPE_ERROR)).not.toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(writes("POST")).toHaveLength(1));
  });

  it("creates a scoped key with the picked deployment", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Dep One" }));
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(writes("POST")).toHaveLength(1));
    expect(writes("POST")[0].data).toMatchObject({
      allow_all_deployments: false,
      api_deployments: ["d1"],
    });
  });

  it("still requires a deployment when 'Allow all' is unchecked", async () => {
    const user = userEvent.setup();
    await openCreateForm(user);

    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText(SCOPE_ERROR)).toBeInTheDocument();
    expect(writes("POST")).toHaveLength(0);
  });
});

describe("GlobalApiDeploymentKeys edit form", () => {
  beforeEach(() => {
    axiosPrivate.mockClear();
  });

  it("opens a scoped key to all deployments", async () => {
    const user = userEvent.setup();
    await openEditForm(user, "ScopedKey");

    await user.click(screen.getByRole("button", { name: /remove dep one/i }));
    await user.click(allowAllBox());
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(writes("PATCH")).toHaveLength(1));
    expect(writes("PATCH")[0].data).toMatchObject({
      allow_all_deployments: true,
      api_deployments: [],
    });
  });

  it("requires a deployment when 'Allow all' is unticked", async () => {
    const user = userEvent.setup();
    await openEditForm(user, "AllKey");

    expect(allowAllBox()).toBeChecked();
    await user.click(allowAllBox());
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(SCOPE_ERROR)).toBeInTheDocument();
    expect(writes("PATCH")).toHaveLength(0);
  });
});
