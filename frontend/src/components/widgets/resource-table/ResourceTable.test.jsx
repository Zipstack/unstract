import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ResourceTable } from "./ResourceTable";

/**
 * ResourceTable renders fine with an empty list — every cell that can throw is
 * inside a row. So the regression this guards against only appears once there
 * is at least one row, which is why an empty-state smoke test missed it and a
 * green build shipped a table that took down /tools and /workflows.
 *
 * The failure: cells wrap values in `<Tooltip>`, whose Radix trigger uses
 * `asChild` and slots onto a single ELEMENT child. Passing a bare string (as
 * antd's Tooltip allowed) throws "Primitive.button failed to slot onto its
 * children", which the route-level error boundary turns into "Couldn't load
 * this page".
 */
const noop = () => undefined;

const ROW = {
  tool_id: "t1",
  tool_name: "Demo Project",
  description: "A demo",
  created_at: "2026-08-01T00:00:00Z",
  modified_at: "2026-08-02T00:00:00Z",
  owner_emails: ["owner@example.com"],
  prompt_count: 2,
};

function renderTable(props = {}) {
  const errors = [];
  const original = console.error;
  console.error = (...args) => {
    errors.push(args.map(String).join(" "));
  };
  try {
    render(
      <MemoryRouter>
        <ResourceTable
          dataSource={[ROW]}
          loading={false}
          pagination={{ current: 1, pageSize: 10, total: 1 }}
          sort={{ sortBy: "modified_at", order: "desc" }}
          userSorted={false}
          titleProp="tool_name"
          descriptionProp="description"
          idProp="tool_id"
          countProp="prompt_count"
          countLabel="Prompts"
          // Present but inert: the actions column only renders its buttons
          // when these are supplied, and the buttons are what carry the
          // Radix triggers under test.
          handleEdit={noop}
          handleShare={noop}
          handleDelete={noop}
          handleCoOwner={noop}
          sessionDetails={{ email: "owner@example.com" }}
          type="Prompt Project"
          {...props}
        />
      </MemoryRouter>,
    );
  } finally {
    console.error = original;
  }
  return errors;
}

describe("ResourceTable", () => {
  it("renders a populated row without a Radix slot violation", () => {
    const errors = renderTable();

    const slotErrors = errors.filter((e) =>
      /failed to slot onto its children/i.test(e),
    );
    expect(
      slotErrors,
      `Radix asChild rejected a non-element child:\n${slotErrors.join("\n")}`,
    ).toEqual([]);
  });

  it("shows the row's content once it has rendered", () => {
    renderTable();
    expect(screen.getByText("Demo Project")).toBeInTheDocument();
  });
});
