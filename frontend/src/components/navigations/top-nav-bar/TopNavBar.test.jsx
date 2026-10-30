import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAlertStore } from "../../../store/alert-store.js";
import { useSessionStore } from "../../../store/session-store.js";
import { ConfirmHost } from "../../widgets/confirm-modal/ConfirmHost.jsx";
import { resetConfirm } from "../../widgets/confirm-modal/confirmStore.js";

vi.mock("axios");

/*
 * The logos are `*.svg?react` imports, which only become components once
 * vite-plugin-svgr runs; it is not in the test pipeline.
 */
vi.mock("../../../assets/index.js", () => ({
  UnstractLogo: () => <span />,
  UnstractBlackLogo: () => <span />,
}));

/*
 * Absent plugins resolve to `export default {}` under vitest (the build throws
 * instead). TopNavBar reads TrialDaysInfo from `default`, so `{}` would reach
 * React as an element type; leave it undefined, as in an OSS build.
 */
vi.mock(
  "../../../plugins/unstract-subscription/components/TrialDaysInfo.jsx",
  () => ({ default: undefined }),
);

const { TopNavBar } = await import("./TopNavBar.jsx");

const ORGS = [
  { id: "org-a", display_name: "Org A" },
  { id: "org-b", display_name: "Org B" },
];

function renderTopNavBar() {
  render(
    <MemoryRouter initialEntries={["/org-a/dashboard"]}>
      <TopNavBar />
      <ConfirmHost />
    </MemoryRouter>,
  );
}

async function openSwitchOrg(user) {
  await user.click(screen.getByTestId("top-navbar-avatar-menu"));
  // The label's element is the nested Dropdown's trigger, which fills the row;
  // the menuitem around it is the parent menu's.
  await screen.findByRole("menuitem", { name: "Switch Org" });
  await user.click(screen.getByText("Switch Org"));
}

beforeEach(() => {
  useAlertStore.setState({ alertDetails: {} });
  useSessionStore.setState({
    sessionDetails: {
      isLoggedIn: true,
      name: "Test User",
      orgName: "org-a",
      orgId: "org-a",
      csrfToken: "csrf",
      allOrganization: ORGS,
    },
  });
});

afterEach(() => {
  resetConfirm();
  vi.clearAllMocks();
});

/*
 * Switch Org is a Dropdown nested inside a row of the profile Dropdown. The
 * org list opens on pointerdown, and the click that follows would select the
 * parent row -- closing the profile menu and unmounting the org list before
 * anything could be picked. These go through user-event's full pointer
 * sequence, which is what a real mouse sends.
 */
describe("TopNavBar Switch Org", () => {
  it("keeps the org list open after a real click", async () => {
    const user = userEvent.setup();
    renderTopNavBar();

    await openSwitchOrg(user);

    expect(await screen.findByText("Org B")).toBeVisible();
    // The profile menu must still be mounted -- the bug unmounted it, taking
    // the org list with it. (Radix aria-hides it while the org list is open.)
    expect(
      screen.getByRole("menuitem", { name: "Switch Org", hidden: true }),
    ).toBeInTheDocument();
  });

  it("switches to the organization picked from the list", async () => {
    axios.mockResolvedValue({});
    const user = userEvent.setup();
    renderTopNavBar();

    await openSwitchOrg(user);
    await user.click(await screen.findByText("Org B"));
    expect(
      await screen.findByText("Want to switch to Org B?"),
    ).toBeInTheDocument();
    expect(useAlertStore.getState().alertDetails).toEqual({});
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "POST",
        url: "/api/v1/organization/org-b/set",
      }),
    );
  });

  it("asks to switch when a keyboard user picks another org", async () => {
    axios.mockResolvedValue({});
    const user = userEvent.setup();
    renderTopNavBar();

    await openSwitchOrg(user);
    const otherOrg = await screen.findByRole("menuitem", { name: "Org B" });
    otherOrg.focus();
    await user.keyboard("{Enter}");
    expect(
      await screen.findByText("Want to switch to Org B?"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));

    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "POST",
        url: "/api/v1/organization/org-b/set",
      }),
    );
  });
});

describe("TopNavBar current org", () => {
  it("tells a keyboard user they are already in the org", async () => {
    const user = userEvent.setup();
    renderTopNavBar();

    await openSwitchOrg(user);
    const currentOrg = await screen.findByRole("menuitem", { name: "Org A" });
    currentOrg.focus();
    await user.keyboard("{Enter}");

    expect(useAlertStore.getState().alertDetails).toMatchObject({
      type: "error",
      content: "You are already in Org A",
    });
    expect(
      screen.queryByText("Want to switch to Org A?"),
    ).not.toBeInTheDocument();
    expect(axios).not.toHaveBeenCalled();
  });

  it("tells a mouse user they are already in the org", async () => {
    const user = userEvent.setup();
    renderTopNavBar();

    await openSwitchOrg(user);
    await user.click(await screen.findByText("Org A"));

    expect(useAlertStore.getState().alertDetails).toMatchObject({
      type: "error",
      content: "You are already in Org A",
    });
    expect(
      screen.queryByText("Want to switch to Org A?"),
    ).not.toBeInTheDocument();
    expect(axios).not.toHaveBeenCalled();
  });
});
