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

  async function openConfirm() {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    );
    return screen.getByRole("alertdialog");
  }

  test("while the switch is in flight Cancel and Escape keep the dialog open", async () => {
    let finish: () => void = () => undefined;
    switchTo.mockReturnValue(
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
    );
    const dialog = await openConfirm();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Switch organisation" }),
    );
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeDisabled();
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    finish();
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
  });

  test("a failed switch enables the confirm button again", async () => {
    switchTo.mockRejectedValue(new Error("HTTP 403"));
    const dialog = await openConfirm();
    const confirm = within(dialog).getByRole("button", {
      name: "Switch organisation",
    });
    await userEvent.click(confirm);
    await screen.findByText("Could not switch. Try again.");
    expect(confirm).toBeEnabled();
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeEnabled();
  });

  test("a 412 from the list means the session is gone: go to sign-in", async () => {
    list.mockRejectedValue({ isAxiosError: true, response: { status: 412 } });
    await open();
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/landing"));
    expect(
      screen.queryByText("Could not load your organisations."),
    ).not.toBeInTheDocument();
  });

  test("a search with no match says so instead of an empty list", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    await screen.findByText("Tanushree’s organisation");
    await userEvent.type(
      screen.getByRole("searchbox", { name: "Find an organisation" }),
      "zzz",
    );
    expect(screen.getByText("No organisations match")).toBeInTheDocument();
    expect(screen.queryByText(/you belong to/i)).not.toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  test("the confirm dialog takes the from side from the current organisation, listed or not", async () => {
    list.mockResolvedValue([personal]);
    switchTo.mockResolvedValue();
    await open();
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Switch to Tanushree’s organisation",
      }),
    );
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Zipstack")).toBeInTheDocument();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Switch organisation" }),
    );
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("/tanushree/tools"),
    );
  });

  test("marks the current row", async () => {
    list.mockResolvedValueOnce([zipstack, personal]);
    await open();
    await screen.findByText("Tanushree’s organisation");
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("aria-current", "true");
    expect(rows[1]).not.toHaveAttribute("aria-current");
  });

  test("the loading text is a polite live region", async () => {
    list.mockReturnValue(new Promise(() => undefined));
    await open();
    expect(await screen.findByText("Loading…")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });

  test("ignores a list response that is not from the latest request", async () => {
    let first: (orgs: Organization[]) => void = () => undefined;
    list
      .mockReturnValueOnce(
        new Promise<Organization[]>((resolve) => {
          first = resolve;
        }),
      )
      .mockResolvedValueOnce([zipstack, personal]);
    await open();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(
      screen.getByRole("button", { name: /Organisation: Zipstack/ }),
    );
    expect(await screen.findByText(/^you belong to 2/i)).toBeInTheDocument();
    first([zipstack]);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByText(/^you belong to 2/i)).toBeInTheDocument();
  });

  test("avatars show two letters for a one-word name, the pill one", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    await screen.findByText("Tanushree’s organisation");
    const rows = screen.getAllByRole("listitem");
    expect(within(rows[0]).getByText("ZI")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Organisation: Zipstack/ }),
    ).toHaveTextContent(/^Z/);
  });

  test("the Switch button carries the arrows icon", async () => {
    list.mockResolvedValue([zipstack, personal]);
    await open();
    const button = await screen.findByRole("button", {
      name: "Switch to Tanushree’s organisation",
    });
    expect(button.querySelector("svg.lucide-arrow-left-right")).not.toBeNull();
  });
});
