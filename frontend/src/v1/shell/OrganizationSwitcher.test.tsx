import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Organization } from "@v1/services/organizations";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { OrganizationSwitcher } from "./OrganizationSwitcher";

const list = vi.fn<() => Promise<Organization[]>>();
const switchTo = vi.fn<(id: string) => Promise<void>>();
vi.mock("@v1/services/organizations", () => ({
  listOrganizations: () => list(),
  switchOrganization: (id: string) => switchTo(id),
}));

const assign = vi.fn();
beforeEach(() => {
  list.mockReset();
  switchTo.mockReset();
  assign.mockReset();
  vi.stubGlobal("location", {
    ...window.location,
    pathname: "/zipstack/tools/42",
    assign,
  });
});
afterEach(() => vi.unstubAllGlobals());

const zipstack: Organization = {
  id: "org_zs",
  name: "zipstack",
  display_name: "Zipstack",
  role: "admin",
  member_count: 40,
  region: "US",
};
const personal: Organization = {
  id: "org_td",
  name: "tanushree",
  display_name: "Tanushree’s organisation",
  role: "admin",
  member_count: 1,
  region: "US",
};
const current = { id: "org_zs", name: "zipstack", displayName: "Zipstack" };

async function open() {
  render(<OrganizationSwitcher current={current} />);
  await userEvent.click(
    screen.getByRole("button", { name: /Organisation: Zipstack/ }),
  );
}

describe("OrganizationSwitcher", () => {
  test("the pill names the current organisation before the list loads", () => {
    list.mockReturnValue(new Promise(() => undefined));
    render(<OrganizationSwitcher current={current} />);
    expect(
      screen.getByRole("button", { name: /Organisation: Zipstack/ }),
    ).toHaveTextContent("Zipstack");
    expect(list).not.toHaveBeenCalled();
  });

  test("lists organisations with role · members · region, current one marked (O01)", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    expect(
      await screen.findByText(/^you belong to 2 organisations$/i),
    ).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("Zipstack")).toBeInTheDocument();
    expect(
      within(rows[0]).getByText("Admin · 40 members · US"),
    ).toBeInTheDocument();
    expect(within(rows[0]).getByText("Current")).toBeInTheDocument();
    expect(
      within(rows[0]).queryByRole("button", { name: /Switch/ }),
    ).not.toBeInTheDocument();
    expect(
      within(rows[1]).getByText("Admin · 1 member · US"),
    ).toBeInTheDocument();
    expect(
      within(rows[1]).getByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    ).toBeInTheDocument();
  });

  test("a member reads Member (O04)", async () => {
    list.mockResolvedValue([{ ...zipstack, role: "user" }, personal]);
    await open();
    expect(
      await screen.findByText("Member · 40 members · US"),
    ).toBeInTheDocument();
  });

  test("one organisation: nothing to switch to (O03)", async () => {
    list.mockResolvedValue([zipstack]);
    await open();
    expect(
      await screen.findByText(/^you belong to 1 organisation$/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Nothing to switch to.")).toBeInTheDocument();
  });

  test("search narrows the rows by name", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    await screen.findByText("Tanushree’s organisation");
    await userEvent.type(
      screen.getByRole("searchbox", { name: "Find an organisation" }),
      "tanu",
    );
    expect(
      screen.queryByText("Zipstack", { selector: "li *" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Tanushree’s organisation")).toBeInTheDocument();
  });

  test("a failed load shows the error with retry; the pill keeps its name", async () => {
    list
      .mockRejectedValueOnce(new Error("HTTP 500"))
      .mockResolvedValueOnce([zipstack, personal]);
    await open();
    expect(
      await screen.findByText("Could not load your organisations."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Organisation: Zipstack/ }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByText("Tanushree’s organisation"),
    ).toBeInTheDocument();
  });

  test("switching asks first (O02), then lands on the same section in the new organisation", async () => {
    list.mockResolvedValue([zipstack, personal]);
    switchTo.mockResolvedValue();
    await open();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    );
    const dialog = screen.getByRole("alertdialog");
    expect(
      within(dialog).getByText("Switch to Tanushree’s organisation?"),
    ).toBeInTheDocument();
    expect(switchTo).not.toHaveBeenCalled();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Switch organisation" }),
    );
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/tanushree/tools"),
    );
    expect(switchTo).toHaveBeenCalledWith("org_td");
  });

  test("cancel switches nothing", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(switchTo).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });

  test("a failed switch says so and stays put", async () => {
    list.mockResolvedValue([zipstack, personal]);
    switchTo.mockRejectedValue(new Error("HTTP 403"));
    await open();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Switch organisation" }),
    );
    expect(
      await screen.findByText("Could not switch. Try again."),
    ).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
