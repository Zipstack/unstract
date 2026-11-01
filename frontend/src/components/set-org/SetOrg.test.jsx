import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("axios");

// `*.svg?react` imports only become components once vite-plugin-svgr runs.
vi.mock("../../assets/index", () => ({
  OrgAvatar: () => <span />,
  OrgSelection: () => <span />,
  RedGradCircle: () => <span />,
  UnstractBlackLogo: () => <span />,
  YellowGradCircle: () => <span />,
}));

const sessionData = vi.fn();
vi.mock("../../hooks/useUserSession.js", () => ({
  useUserSession: () => sessionData,
}));

// Navigating away would end the test page; the URL is covered in
// helpers/orgSwitchLogin.test.js.
vi.mock("../../helpers/orgSwitchLogin.js", async (importOriginal) => ({
  ...(await importOriginal()),
  switchOrgViaLogin: vi.fn(),
}));

const { SetOrg } = await import("./SetOrg.jsx");
const { switchOrgViaLogin } = await import("../../helpers/orgSwitchLogin.js");

const ORGS = [
  { id: "org-a", display_name: "Org A" },
  { id: "org-b", display_name: "Org B" },
];

async function pickOrgB(session) {
  sessionData.mockResolvedValue(session);
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[{ pathname: "/setOrg", state: ORGS }]}>
      <SetOrg />
    </MemoryRouter>,
  );
  const connect = screen.getAllByRole("button", { name: /Connect/ })[1];
  await waitFor(() => expect(connect).toBeEnabled());
  await user.click(connect);
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SetOrg", () => {
  it("sets the picked organization locally on a session without the login flag", async () => {
    axios.mockResolvedValue({});

    await pickOrgB({ organization_id: null });

    expect(axios).toHaveBeenCalledWith(
      expect.objectContaining({
        method: "POST",
        url: "/api/v1/organization/org-b/set",
      }),
    );
    expect(switchOrgViaLogin).not.toHaveBeenCalled();
  });

  it("keeps Connect disabled until the session has loaded", async () => {
    let resolveSession;
    sessionData.mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve;
      }),
    );
    render(
      <MemoryRouter initialEntries={[{ pathname: "/setOrg", state: ORGS }]}>
        <SetOrg />
      </MemoryRouter>,
    );
    const buttons = screen.getAllByRole("button", { name: /Connect/ });
    for (const button of buttons) {
      expect(button).toBeDisabled();
    }

    resolveSession({ organization_id: null, org_switch_via_login: true });

    await waitFor(() => {
      for (const button of buttons) {
        expect(button).toBeEnabled();
      }
    });
  });

  it("leaves the picker without a pick when the session cannot be read", async () => {
    sessionData.mockRejectedValue(new Error("session unavailable"));
    render(
      <MemoryRouter initialEntries={[{ pathname: "/setOrg", state: ORGS }]}>
        <SetOrg />
      </MemoryRouter>,
    );
    for (const button of screen.getAllByRole("button", { name: /Connect/ })) {
      expect(button).toBeDisabled();
    }

    // Navigating to "/" drops the organizations, so no Connect is left to click.
    await waitFor(() =>
      expect(screen.queryAllByRole("button", { name: /Connect/ })).toHaveLength(
        0,
      ),
    );
    expect(axios).not.toHaveBeenCalled();
    expect(switchOrgViaLogin).not.toHaveBeenCalled();
  });

  it("logs in again naming the picked organization when the session asks", async () => {
    await pickOrgB({ organization_id: null, org_switch_via_login: true });

    await waitFor(() =>
      expect(switchOrgViaLogin).toHaveBeenCalledWith("org-b"),
    );
    expect(axios).not.toHaveBeenCalled();
  });
});
