import { useQuery } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
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
import { Component, type JSX, type ReactNode } from "react";
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

it("keeps the data on screen, with no alert, when a refresh fails", async () => {
  const toast = vi.spyOn(console, "error").mockImplementation(() => undefined);
  mockApi(...adapterHandlers(DEFAULT_SESSION));
  function Refreshable(): JSX.Element {
    const query = useQuery(adapterQueries.list({ adapterType: "LLM" }));
    return (
      <>
        <p>Status {query.status}</p>
        <button type="button" onClick={() => void query.refetch()}>
          Refresh
        </button>
        <QueryView query={query}>
          {(rows) => <p>{rows.map((row) => row.adapter_name).join(", ")}</p>}
        </QueryView>
      </>
    );
  }
  const { user } = renderV1(<Refreshable />);
  expect(await screen.findByText("OpenAI GPT-4o, Claude")).toBeInTheDocument();
  mockApi(mock.get(ADAPTERS, () => HttpResponse.json({}, { status: 500 })));
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(screen.getByText("Status error")).toBeInTheDocument(),
  );
  expect(screen.getByText("OpenAI GPT-4o, Claude")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  // No notifier is mounted, so the toast falls back to the console.
  expect(toast).toHaveBeenCalledTimes(1);
});

it("renders a successful query whose select gives undefined, not an alert", async () => {
  mockApi(...adapterHandlers(DEFAULT_SESSION));
  function Pick(): JSX.Element {
    const query = useQuery({
      ...adapterQueries.list({ adapterType: "LLM" }),
      select: (rows) => rows.find((row) => row.adapter_name === "Mistral"),
    });
    return (
      <QueryView query={query}>
        {(row) => <p>{row?.adapter_name ?? "No match"}</p>}
      </QueryView>
    );
  }
  renderV1(<Pick />);
  expect(await screen.findByText("No match")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("reports a failed refresh once, as a toast, when select gave undefined", async () => {
  const toast = vi.spyOn(console, "error").mockImplementation(() => undefined);
  mockApi(...adapterHandlers(DEFAULT_SESSION));
  function Pick(): JSX.Element {
    const query = useQuery({
      ...adapterQueries.list({ adapterType: "LLM" }),
      select: (rows) => rows.find((row) => row.adapter_name === "Mistral"),
    });
    return (
      <>
        <p>Status {query.status}</p>
        <button type="button" onClick={() => void query.refetch()}>
          Refresh
        </button>
        <QueryView query={query}>
          {(row) => <p>{row?.adapter_name ?? "No match"}</p>}
        </QueryView>
      </>
    );
  }
  const { user } = renderV1(<Pick />);
  expect(await screen.findByText("No match")).toBeInTheDocument();
  mockApi(mock.get(ADAPTERS, () => HttpResponse.json({}, { status: 500 })));
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(screen.getByText("Status error")).toBeInTheDocument(),
  );
  expect(screen.getByText("No match")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(toast).toHaveBeenCalledTimes(1);
});

class Boundary extends Component<{ children: ReactNode }, { error?: Error }> {
  override state: { error?: Error } = {};

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  override render(): ReactNode {
    return this.state.error ? (
      <p>Caught {this.state.error.message}</p>
    ) : (
      this.props.children
    );
  }
}

it("leaves a select that throws to the error boundary", async () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  mockApi(...adapterHandlers(DEFAULT_SESSION));
  function Broken(): JSX.Element {
    const query = useQuery({
      ...adapterQueries.list({ adapterType: "LLM" }),
      select: (): never => {
        throw new TypeError("bad select");
      },
    });
    return <QueryView query={query}>{() => <p>Rows</p>}</QueryView>;
  }
  renderV1(
    <Boundary>
      <Broken />
    </Boundary>,
  );
  expect(await screen.findByText("Caught bad select")).toBeInTheDocument();
});
