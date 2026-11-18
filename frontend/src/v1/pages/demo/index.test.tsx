import { screen } from "@testing-library/react";
import { setOrganizationId } from "@v1/services/context";
import { DEFAULT_SESSION, mockApi, renderV1 } from "@v1/test";
import { adapterFixtures, adapterHandlers } from "@v1/test/fixtures/adapters";
import { afterEach, expect, it } from "vitest";
import { DemoPage } from "./index";

const ORG = DEFAULT_SESSION.organization.id;
const at = { route: `/${ORG}/v1-demo`, path: "/:orgName/v1-demo" };

afterEach(() => setOrganizationId(null));

it("lists the organisation's LLM adapters through the sample service", async () => {
  const seen: URL[] = [];
  mockApi(...adapterHandlers(DEFAULT_SESSION, adapterFixtures.llm, seen));
  const { container } = renderV1(<DemoPage />, at);
  expect(await screen.findByText("OpenAI GPT-4o")).toBeInTheDocument();
  expect(screen.getByText("Claude")).toBeInTheDocument();
  expect(seen[0]?.pathname).toBe(`/api/v1/unstract/${ORG}/adapter/`);
  expect(seen[0]?.searchParams.get("adapter_type")).toBe("LLM");
  await expect(container).toHaveNoA11yViolations();
});

it("says so when there are none", async () => {
  mockApi(...adapterHandlers(DEFAULT_SESSION, []));
  renderV1(<DemoPage />, at);
  expect(await screen.findByText("No LLM adapters yet.")).toBeInTheDocument();
});
