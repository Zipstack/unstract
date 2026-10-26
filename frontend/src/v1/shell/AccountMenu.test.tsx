import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { AccountMenu } from "./AccountMenu";

const signOut = vi.fn<() => Promise<string>>();
vi.mock("@v1/services/session", () => ({ signOut: () => signOut() }));
const reset = vi.fn();
vi.mock("posthog-js", () => ({ default: { reset: () => reset() } }));

const assign = vi.fn();
beforeEach(() => {
  signOut.mockReset();
  reset.mockReset();
  assign.mockReset();
  vi.stubGlobal("location", { ...window.location, assign });
});
afterEach(() => vi.unstubAllGlobals());

const user = { name: "Tanushree Daga", email: "tanushree@zipstack.com" };

async function open() {
  render(<AccountMenu user={user} profileHref="/zipstack/profile" />);
  await userEvent.click(screen.getByRole("button", { name: "Account menu" }));
}

describe("AccountMenu", () => {
  test("the trigger shows the user's initials", () => {
    render(<AccountMenu user={user} profileHref="/zipstack/profile" />);
    expect(
      screen.getByRole("button", { name: "Account menu" }),
    ).toHaveTextContent("TD");
  });

  test("lists identity, profile, help and sign out, as frame NEW09 shows", async () => {
    await open();
    expect(screen.getByText("Tanushree Daga")).toBeInTheDocument();
    expect(screen.getByText("tanushree@zipstack.com")).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Profile & preferences" }),
    ).toHaveAttribute("href", "/zipstack/profile");
    expect(
      screen.getByRole("menuitem", { name: /Help & docs/ }),
    ).toHaveAttribute("href", "https://docs.unstract.com");
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
    expect(lines[0]).toHaveClass("font-semibold");
  });

  test("OSS has no Plan & billing item and no version switch (D14)", async () => {
    await open();
    expect(screen.queryByText("Plan & billing")).not.toBeInTheDocument();
    expect(screen.queryByText(/old version/i)).not.toBeInTheDocument();
  });

  test("sign out ends the session, resets analytics and opens the returned URL", async () => {
    signOut.mockResolvedValue("https://id.example.com/v2/logout");
    await open();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith("https://id.example.com/v2/logout"),
    );
    expect(reset).toHaveBeenCalled();
  });

  test("a failed sign-out falls back to the GET logout, which still ends the session", async () => {
    signOut.mockRejectedValue(new Error("HTTP 403"));
    await open();
    await userEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/api/v1/logout"));
  });
});
