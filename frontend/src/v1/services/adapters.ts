import { keepPreviousData, queryOptions } from "@tanstack/react-query";
import { currentOrganizationId, orgPath } from "./context";
import { http, type RequestOptions } from "./http";
import { type Page, type PageParams, pageQuery } from "./page";

/* Adapters (LLM, embedding, vector DB, text extractor, OCR) in the current organisation. */

export const ADAPTER_TYPES = [
  "LLM",
  "EMBEDDING",
  "VECTOR_DB",
  "X2TEXT",
  "OCR",
] as const;
export type AdapterType = (typeof ADAPTER_TYPES)[number];

/** A row of `GET adapter/`; the fields v1 reads. */
export type Adapter = Readonly<{
  id: string;
  adapter_id: string;
  adapter_name: string;
  adapter_type: AdapterType;
  description: string | null;
  icon: string;
  created_at: string;
  modified_at: string;
}>;

export type ListAdaptersParams = Readonly<{
  adapterType: AdapterType;
  search?: string;
}>;

export type ListAdaptersPageParams = ListAdaptersParams & PageParams;

/** A page of adapters; the endpoint adds the failing count across all pages. */
export type AdapterPage = Page<Adapter> & Readonly<{ failing_count: number }>;

const filterQuery = (params: ListAdaptersParams) => ({
  adapter_type: params.adapterType,
  search: params.search,
});

/** `GET /api/v1/unstract/<org>/adapter/`, unpaged. */
export async function listAdapters(
  params: ListAdaptersParams,
  { signal }: RequestOptions = {},
): Promise<Adapter[]> {
  const { data } = await http.get<Adapter[]>(orgPath("/adapter/"), {
    params: filterQuery(params),
    signal,
  });
  return data;
}

/** The same list, one page at a time. */
export async function listAdaptersPage(
  params: ListAdaptersPageParams,
  { signal }: RequestOptions = {},
): Promise<AdapterPage> {
  const { data } = await http.get<AdapterPage>(orgPath("/adapter/"), {
    params: { ...filterQuery(params), ...pageQuery(params) },
    signal,
  });
  return data;
}

/** Query keys: `[org, "adapters", "list" | "page" | "detail", params | id]`. */
export const adapterKeys = {
  all: () => [currentOrganizationId(), "adapters"] as const,
  list: (params: ListAdaptersParams) =>
    [...adapterKeys.all(), "list", params] as const,
  page: (params: ListAdaptersPageParams) =>
    [...adapterKeys.all(), "page", params] as const,
};

export const adapterQueries = {
  list: (params: ListAdaptersParams) =>
    queryOptions({
      queryKey: adapterKeys.list(params),
      queryFn: ({ signal }) => listAdapters(params, { signal }),
    }),
  // The previous page stays on screen while the next one loads.
  page: (params: ListAdaptersPageParams) =>
    queryOptions({
      queryKey: adapterKeys.page(params),
      queryFn: ({ signal }) => listAdaptersPage(params, { signal }),
      placeholderData: keepPreviousData,
    }),
};
