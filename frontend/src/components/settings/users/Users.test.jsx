import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Manage Users' kebab menu, and which ROW its entries act on.
 *
 * The row used to be recorded by an `onClick` on the kebab icon itself — the
 * Dropdown's trigger. Radix opens the menu on POINTERDOWN and pins
 * `pointer-events: none` on <body> for as long as it is open, so the click
 * that would have followed never lands and the handler never runs. Edit
 * therefore navigated to /users/edit carrying `state: undefined`, and
 * InviteEditUser bounces a stateless edit straight to the dashboard: the Edit
 * action looked like it did nothing but log you out of the page. Delete's
 * confirmation named no user at all.
 *
 * jsdom does no hit-testing, so it would dispatch that swallowed click
 * happily — which is exactly why these tests drive the MENU ENTRY rather than
 * the icon. Reaching the entry is the part a real browser allows; binding the
 * row to it is the part under test.
 */
const navigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});

const MEMBERS = [
  { id: "1", email: "ada@example.com", role: "unstract_admin" },
  { id: "2", email: "grace@example.com", role: "unstract_user" },
];

vi.mock("../../../hooks/useAxiosPrivate", () => ({
  useAxiosPrivate: () => () => Promise.resolve({ data: { members: MEMBERS } }),
}));

vi.mock("../../../hooks/useExceptionHandler.jsx", () => ({
  useExceptionHandler: () => (err, fallback) => ({ content: fallback }),
}));

vi.mock("../../../hooks/usePostHogEvents.js", () => ({
  default: () => ({ setPostHogCustomEvent: () => undefined }),
}));

vi.mock("../../../store/alert-store", () => ({
  useAlertStore: () => ({ setAlertDetails: () => undefined }),
}));

vi.mock("../../../store/session-store", () => ({
  useSessionStore: () => ({
    sessionDetails: { orgId: "org-1", orgName: "my-org", csrfToken: "tok" },
  }),
}));

const { Users } = await import("./Users.jsx");

/** Opens the kebab on the given row and returns the menu entry by name. */
async function openRowMenu(rowEmail, entry) {
  render(
    <MemoryRouter>
      <Users />
    </MemoryRouter>,
  );
  await screen.findByText(rowEmail);

  const row = screen.getByText(rowEmail).closest("tr");
  // Radix's trigger toggles on pointerdown, not click — as in the browser.
  fireEvent.pointerDown(row.querySelector(".ant-dropdown-trigger"), {
    button: 0,
    ctrlKey: false,
    pointerType: "mouse",
  });

  return await screen.findByText(entry);
}

describe("Manage Users kebab menu", () => {
  beforeEach(() => {
    navigate.mockReset();
  });

  it("sends the clicked row to the edit page", async () => {
    fireEvent.click(await openRowMenu("grace@example.com", "Edit"));

    expect(navigate).toHaveBeenCalledWith("/my-org/users/edit", {
      state: expect.objectContaining({
        email: "grace@example.com",
        role: "unstract_user",
      }),
    });
  });

  it("edits the row whose kebab was opened, not the first one", async () => {
    fireEvent.click(await openRowMenu("ada@example.com", "Edit"));

    expect(navigate).toHaveBeenCalledWith("/my-org/users/edit", {
      state: expect.objectContaining({ email: "ada@example.com" }),
    });
  });

  it("names the clicked row in the delete confirmation", async () => {
    fireEvent.click(await openRowMenu("grace@example.com", "Delete"));

    await waitFor(() =>
      expect(screen.getByText("Delete User")).toBeInTheDocument(),
    );
    // The row's email appears twice once the modal is up: table cell + modal.
    expect(screen.getAllByText("grace@example.com").length).toBeGreaterThan(1);
  });
});
