import { http, orgPath, type RequestOptions } from "./http";

export type User = Readonly<{ id: string; email: string }>;

export async function listUsers({
  signal,
}: RequestOptions = {}): Promise<User[]> {
  const { data } = await http.get<User[]>(orgPath("/users/"), { signal });
  return data;
}

export const LOGOUT_URL = "/api/v1/logout";
