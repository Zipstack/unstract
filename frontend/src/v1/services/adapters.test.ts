import { QueryClient } from "@tanstack/react-query";
import { DEFAULT_SESSION, makeSession, mockApi } from "@v1/test";
import { adapterFixtures, adapterHandlers } from "@v1/test/fixtures/adapters";
import { afterEach, expect, it } from "vitest";
import {
  adapterKeys,
  adapterQueries,
  listAdapters,
  listAdaptersPage,
} from "./adapters";
import { setOrganizationId } from "./context";

afterEach(() => setOrganizationId(null));

it("lists the organisation's adapters of one type, with typed params", async () => {
  setOrganizationId(DEFAULT_SESSION.organization.id);
  const seen: URL[] = [];
  mockApi(...adapterHandlers(DEFAULT_SESSION, adapterFixtures.llm, seen));
  const rows = await listAdapters({ adapterType: "LLM", search: "gpt" });
  expect(rows).toEqual(adapterFixtures.llm);
  expect(seen[0]?.pathname).toBe("/api/v1/unstract/org-1/adapter/");
  expect(Object.fromEntries(seen[0]?.searchParams ?? [])).toEqual({
    adapter_type: "LLM",
    search: "gpt",
  });
});

it("sends no search parameter when none is given", async () => {
  setOrganizationId(DEFAULT_SESSION.organization.id);
  const seen: URL[] = [];
  mockApi(...adapterHandlers(DEFAULT_SESSION, [], seen));
  await listAdapters({ adapterType: "OCR" });
  expect(seen[0]?.search).toBe("?adapter_type=OCR");
});

it("fetches one page with typed page params", async () => {
  setOrganizationId(DEFAULT_SESSION.organization.id);
  const seen: URL[] = [];
  mockApi(...adapterHandlers(DEFAULT_SESSION, adapterFixtures.llm, seen));
  const page = await listAdaptersPage({
    adapterType: "LLM",
    page: 2,
    pageSize: 1,
  });
  expect(Object.fromEntries(seen[0]?.searchParams ?? [])).toEqual({
    adapter_type: "LLM",
    page: "2",
    page_size: "1",
  });
  expect(page).toMatchObject({
    count: 2,
    next: null,
    results: [adapterFixtures.llm[1]],
    failing_count: 0,
  });
  expect(page.previous).toContain("page=1");
});

it("keys queries by organisation, so two organisations never share a cache entry", () => {
  const params = { adapterType: "LLM" } as const;
  setOrganizationId("org-1");
  const first = adapterQueries.list(params).queryKey;
  setOrganizationId(
    makeSession({ organization: { id: "org-2" } }).organization.id,
  );
  const second = adapterQueries.list(params).queryKey;
  expect(first).toEqual(["org-1", "adapters", "list", params]);
  expect(second).toEqual(["org-2", "adapters", "list", params]);
  expect(adapterKeys.all()).toEqual(["org-2", "adapters"]);
  expect(
    adapterQueries.page({ ...params, page: 1, pageSize: 10 }).queryKey,
  ).toEqual([
    "org-2",
    "adapters",
    "page",
    { ...params, page: 1, pageSize: 10 },
  ]);
});

// Each builds its query now and returns a run that fetches it later.
const queries = {
  list: () => {
    const options = adapterQueries.list({ adapterType: "LLM" });
    return () => new QueryClient().fetchQuery(options);
  },
  page: () => {
    const params = { adapterType: "LLM", page: 1, pageSize: 10 } as const;
    const options = adapterQueries.page(params);
    return () => new QueryClient().fetchQuery(options);
  },
};

it.each(
  Object.entries(queries),
)("%s fetches for the organisation in its key, even after the current one changes", async (_, build) => {
  setOrganizationId("org-1");
  const run = build();
  setOrganizationId("org-2");
  const seen: URL[] = [];
  mockApi(...adapterHandlers(DEFAULT_SESSION, adapterFixtures.llm, seen));
  await run();
  expect(seen[0]?.pathname).toBe("/api/v1/unstract/org-1/adapter/");
});
