import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CreateNotification } from "./CreateNotification.jsx";

/**
 * The webhook's authorization key is a credential the receiving endpoint
 * trusts. Editing a notification loads it back into the form, so a plain
 * text input would put it on screen every time the form opens.
 */
const TOKEN = "whk_7f3a9c21d84b4e06a5b2c1d0e9f8a7b6";

const renderForm = (editDetails) =>
  render(
    <CreateNotification
      setIsForm={vi.fn()}
      type="api"
      id="dep-1"
      isLoading={false}
      handleSubmit={vi.fn()}
      handleUpdate={vi.fn()}
      editDetails={editDetails}
    />,
  );

describe("CreateNotification authorization key", () => {
  it("is masked when an existing notification is edited", () => {
    const { container } = renderForm({
      id: "n-1",
      name: "hook",
      url: "https://example.com/hook",
      authorization_type: "BEARER",
      authorization_key: TOKEN,
      authorization_header: "",
      max_retries: 0,
      platform: "API",
      notification_type: "WEBHOOK",
      is_active: true,
    });

    const input = container.querySelector("#authorization_key");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("autocomplete", "new-password");
    // Today's behaviour, not the goal: the API still returns the stored key,
    // so it is the input's value and editing keeps it. Once the API returns
    // a placeholder and treats an unchanged value as "keep existing"
    // (UN-4562), assert the placeholder here instead.
    expect(input).toHaveValue(TOKEN);
  });

  it("can be revealed on request", () => {
    const { container } = renderForm();

    fireEvent.click(screen.getByLabelText("Show password"));

    expect(container.querySelector("#authorization_key")).toHaveAttribute(
      "type",
      "text",
    );
  });
});
