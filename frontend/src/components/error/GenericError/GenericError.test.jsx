import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { GenericError } from "./GenericError.jsx";

function renderAt(url) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/error" element={<GenericError />} />
        <Route path="/" element={<p>App home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("GenericError", () => {
  it.each([
    "/error?code=INS",
    "/error?code=IDM",
    "/error",
  ])("offers a way back to the app on %s", async (url) => {
    const user = userEvent.setup();
    renderAt(url);

    await user.click(screen.getByRole("button", { name: "Back to home" }));

    expect(screen.getByText("App home")).toBeInTheDocument();
  });

  it("still shows the message for the code", () => {
    renderAt("/error?code=INS");

    expect(screen.getByText("Access Denied")).toBeInTheDocument();
  });
});
