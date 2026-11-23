/* Fixtures for services/adapters, typed against its contract. */

import type { Adapter, AdapterPage } from "@v1/services/adapters";
import { apiPath, HttpResponse, http, type TestSession } from "@v1/test";

export const adapterFixtures = {
  llm: [
    {
      id: "4f0c2a8e-1d6b-4a51-9a39-6a3c1d2b7e10",
      adapter_id: "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17",
      adapter_name: "OpenAI GPT-4o",
      adapter_type: "LLM",
      description: null,
      icon: "/icons/adapter-icons/OpenAI.png",
      created_at: "2026-11-01T10:00:00Z",
      modified_at: "2026-11-02T10:00:00Z",
    },
    {
      id: "9b7e5c3a-2f4d-4c1b-8e6a-0d9f8c7b6a51",
      adapter_id: "anthropic|90ebd4cd-2f19-4cef-a884-9eeb6ac0f203",
      adapter_name: "Claude",
      adapter_type: "LLM",
      description: "Default extraction model",
      icon: "/icons/adapter-icons/Anthropic.png",
      created_at: "2026-11-03T10:00:00Z",
      modified_at: "2026-11-03T10:00:00Z",
    },
  ],
} satisfies Record<string, Adapter[]>;

/* The link to `page`, or null when it is out of range; DRF drops `page` for page 1. */
function pageLink(url: URL, page: number, last: number): string | null {
  if (page < 1 || page > last) {
    return null;
  }
  const link = new URL(url);
  if (page === 1) {
    link.searchParams.delete("page");
  } else {
    link.searchParams.set("page", String(page));
  }
  return link.href;
}

// DRF's NotFound for a page past the end, as drf-standardized-errors shapes it.
const INVALID_PAGE = {
  type: "client_error",
  errors: [{ code: "not_found", detail: "Invalid page.", attr: null }],
};

/* As the backend pages it: an envelope only when asked for a page; null past the end. */
function answer(
  url: URL,
  rows: readonly Adapter[],
): readonly Adapter[] | AdapterPage | null {
  const page = Number(url.searchParams.get("page") || 0);
  const size = Number(url.searchParams.get("page_size") || 0);
  if (!page && !size) {
    return rows;
  }
  const current = page || 1;
  const perPage = size || 50;
  const last = Math.ceil(rows.length / perPage);
  if (current > Math.max(1, last)) {
    return null;
  }
  return {
    count: rows.length,
    next: pageLink(url, current + 1, last),
    previous: pageLink(url, current - 1, last),
    results: rows.slice((current - 1) * perPage, current * perPage),
    failing_count: 0,
  };
}

/** `GET adapter/` answering `rows`, paged on request; records each URL in `seen`. */
export const adapterHandlers = (
  session: TestSession,
  rows: readonly Adapter[] = adapterFixtures.llm,
  seen: URL[] = [],
) => [
  http.get(apiPath(session, "/adapter/"), ({ request }) => {
    const url = new URL(request.url);
    seen.push(url);
    const body = answer(url, rows);
    return body === null
      ? HttpResponse.json(INVALID_PAGE, { status: 404 })
      : HttpResponse.json(body);
  }),
];
