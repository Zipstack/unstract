import { http, orgPath, type RequestOptions } from "@v1/services/http";

export type Plan = Readonly<{ id: string; name: string }>;

export async function listPlans({ signal }: RequestOptions = {}) {
  const { data } = await http.get<Plan[]>(orgPath("/plans/"), { signal });
  return data;
}

export const PLANS_PAGE = "/api/v1/billing/plans/";
