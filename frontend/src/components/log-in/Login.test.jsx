import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// `*.svg?react` imports only become components once vite-plugin-svgr runs.
vi.mock("../../assets", () => ({ UnstractBlackLogo: () => <span /> }));
vi.mock("../../assets/login-right-panel.svg", () => ({ default: "" }));

const { Login } = await import("./Login.jsx");

const ORIGIN = "http://localhost:3000";
const realLocation = window.location;
let assignedHref;

beforeEach(() => {
  assignedHref = undefined;
  // Following the login link would end the test page; record it instead.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      origin: ORIGIN,
      get href() {
        return `${ORIGIN}/landing`;
      },
      set href(value) {
        assignedHref = value;
      },
    },
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: realLocation,
  });
  localStorage.clear();
});

async function clickLogin(from) {
  const user = userEvent.setup();
  render(
    <MemoryRouter
      initialEntries={[{ pathname: "/landing", state: from && { from } }]}
    >
      <Login />
    </MemoryRouter>,
  );
  await user.click(screen.getByRole("button", { name: "Login" }));
  return new URL(assignedHref);
}

describe("Login", () => {
  it("sends the page the visitor asked for as redirect_url", async () => {
    const url = await clickLogin({
      pathname: "/acme/workflows",
      search: "?tab=runs",
    });

    expect(url.pathname).toBe("/api/v1/login");
    expect(url.searchParams.get("redirect_url")).toBe(
      "/acme/workflows?tab=runs",
    );
    expect(url.search).toBe(
      `?redirect_url=${encodeURIComponent("/acme/workflows?tab=runs")}`,
    );
  });

  it("keeps the product alongside the redirect", async () => {
    localStorage.setItem("selectedProduct", "unstract");

    const url = await clickLogin({ pathname: "/acme/workflows" });

    expect(url.searchParams.get("selectedProduct")).toBe("unstract");
    expect(url.searchParams.get("redirect_url")).toBe("/acme/workflows");
  });

  it.each([
    ["no earlier page", undefined],
    ["a protocol-relative path", { pathname: "//evil.example/x" }],
    ["an absolute URL", { pathname: "https://evil.example/x" }],
  ])("leaves redirect_url off for %s", async (_label, from) => {
    const url = await clickLogin(from);

    expect(url.toString()).toBe(`${ORIGIN}/api/v1/login`);
  });
});
