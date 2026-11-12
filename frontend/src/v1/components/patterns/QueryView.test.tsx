import { useQuery } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { adapterQueries } from "@v1/services/adapters";
import { setOrganizationId } from "@v1/services/context";
import {
  apiPath,
  DEFAULT_SESSION,
  delay,
  HttpResponse,
  http as mock,
  mockApi,
  renderV1,
} from "@v1/test";
import { adapterFixtures, adapterHandlers } from "@v1/test/fixtures/adapters";
import type { JSX } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { QueryView } from "./QueryView";

const ADAPTERS = apiPath(DEFAULT_SESSION, "/adapter/");

function Names(): JSX.Element {
  const query = useQuery(adapterQueries.list({ adapterType: "LLM" }));
  return (
    <QueryView query={query}>
      {(rows) => <p>{rows.map((row) => row.adapter_name).join(", ")}</p>}
    </QueryView>
  );
}

beforeEach(() => setOrganizationId(DEFAULT_SESSION.organization.id));
afterEach(() => setOrganizationId(null));

it("shows a skeleton while loading, then the data", async () => {
  mockApi(
    mock.get(ADAPTERS, async () => {
      await delay(20);
      return HttpResponse.json(adapterFixtures.llm);
    }),
  );
  const { container } = renderV1(<Names />);
  expect(container.querySelector("[data-slot='skeleton-text']")).not.toBeNull();
  expect(await screen.findByText("OpenAI GPT-4o, Claude")).toBeInTheDocument();
});

it("shows the error with its request id, and Retry fetches again", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
  mockApi(
    mock.get(
      ADAPTERS,
      () =>
        HttpResponse.json(
          { error: "Database down" },
          { status: 500, headers: { "X-Request-ID": "req-42" } },
        ),
      { once: true },
    ),
    ...adapterHandlers(DEFAULT_SESSION),
  );
  const { user, container } = renderV1(<Names />);
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Database down");
  expect(alert).toHaveTextContent("Request ID req-42");
  await expect(container).toHaveNoA11yViolations();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("OpenAI GPT-4o, Claude")).toBeInTheDocument();
});

it("takes a custom loading view", () => {
  mockApi(
    mock.get(ADAPTERS, async () => {
      await delay(20);
      return HttpResponse.json([]);
    }),
  );
  function Custom(): JSX.Element {
    const query = useQuery(adapterQueries.list({ adapterType: "LLM" }));
    return (
      <QueryView query={query} loading={<p>Loading adapters</p>}>
        {() => null}
      </QueryView>
    );
  }
  renderV1(<Custom />);
  expect(screen.getByText("Loading adapters")).toBeInTheDocument();
});
