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
  await waitFor(() => expect(sessionData).toHaveBeenCalled());
  const connect = screen.getAllByRole("button", { name: /Connect/ })[1];
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

  it("logs in again naming the picked organization when the session asks", async () => {
    await pickOrgB({ organization_id: null, org_switch_via_login: true });

    await waitFor(() =>
      expect(switchOrgViaLogin).toHaveBeenCalledWith("org-b"),
    );
    expect(axios).not.toHaveBeenCalled();
  });
});
