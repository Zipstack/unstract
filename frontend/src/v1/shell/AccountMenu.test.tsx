import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const signOutAndLeave = vi.fn<() => Promise<void>>();
vi.mock("@v1/services/session", () => ({
  signOutAndLeave: () => signOutAndLeave(),
}));

beforeEach(() => signOutAndLeave.mockReset());

const user = { name: "Tanushree Daga", email: "tanushree@zipstack.com" };

async function open() {
  render(<AccountMenu user={user} profileHref="/zipstack/profile" />);
  await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
}

describe("AccountMenu", () => {
  test("the trigger shows one letter; the menu header keeps two-letter initials", async () => {
    render(<AccountMenu user={user} profileHref="/zipstack/profile" />);
    const trigger = screen.getByRole("button", { name: "Account menu" });
    expect(trigger).toHaveTextContent(/^T$/);
    await userEvent.click(trigger);
    expect(screen.getByText("TD")).toBeInTheDocument();
  });

  test("a user without a name gets the e-mail's first letter on the trigger", () => {
    render(
      <AccountMenu
        user={{ name: "", email: "athul@zipstack.com" }}
        profileHref="/zipstack/profile"
      />,
    );
    expect(
      screen.getByRole("button", { name: "Account menu" }),
    ).toHaveTextContent(/^A$/);
  });

  test("lists identity, profile, help and sign out, as frame NEW09 shows", async () => {
    await open();
    // The Unstract theme's sidebar is navy under dark text.
    expect(screen.getByRole("menu")).toHaveClass("ui:bg-popover");
    expect(screen.getByText("Tanushree Daga")).toBeInTheDocument();
    expect(screen.getByText("tanushree@zipstack.com")).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Profile & preferences" }),
    ).toHaveAttribute("href", "/zipstack/profile");
    expect(
      screen.getByRole("menuitem", { name: /Help & docs/ }),
    ).toHaveAttribute("href", "https://docs.unstract.com");
    expect(
      screen.getByRole("menuitem", {
        name: "Help & docs (opens in a new tab)",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Sign out" }),
    ).toBeInTheDocument();
  });

  test("a user without a name shows the e-mail once, in the name's place", async () => {
    render(
      <AccountMenu
        user={{ name: "", email: "athul@zipstack.com" }}
        profileHref="/zipstack/profile"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
    const lines = screen.getAllByText("athul@zipstack.com");
    expect(lines).toHaveLength(1);
    // The bold title line, not an empty title above the e-mail.
    expect(lines[0]).toHaveClass("ui:font-semibold");
  });

  test("OSS has no Plan & billing item and no version switch (D14)", async () => {
    await open();
    expect(screen.queryByText("Plan & billing")).not.toBeInTheDocument();
    expect(screen.queryByText(/old version/i)).not.toBeInTheDocument();
  });

  test("sign out hands over to the shared sign-out sequence", async () => {
    signOutAndLeave.mockResolvedValue();
    await open();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(signOutAndLeave).toHaveBeenCalledTimes(1));
  });
});
