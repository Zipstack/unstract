import { queryOptions } from "@tanstack/react-query";
import type { Capability } from "@v1/lib/permissions";
import { currentOrganizationId } from "./context";
import { http, orgPath, type RequestOptions } from "./http";

/* What the organisation's capability settings let the signed-in user do. */

/** `GET /api/v1/unstract/<org>/organization/capabilities/`. */
export async function listCapabilities({
  signal,
  org,
}: RequestOptions = {}): Promise<readonly Capability[]> {
  const { data } = await http.get<{ capabilities?: Capability[] }>(
    orgPath("/organization/capabilities/", org),
    { signal },
  );
  if (!Array.isArray(data?.capabilities)) {
    throw new TypeError("Capabilities reply carried no capabilities");
  }
  return data.capabilities;
}

/** Query keys: `[org, "capabilities"]`. */
export const capabilityKeys = {
  all: () => [currentOrganizationId(), "capabilities"] as const,
};

/** Read with `canCreate()`, or `canDeleteWorkflowOrDeployment()` for the delete capability, from `@v1/lib/permissions`. */
export const capabilityQueries = {
  list: () =>
    queryOptions({
      queryKey: capabilityKeys.all(),
      queryFn: ({ queryKey: [org], signal }) =>
        listCapabilities({ signal, org }),
    }),
};
