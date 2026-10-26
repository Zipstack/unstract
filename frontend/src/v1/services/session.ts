import { http } from "@v1/lib/http";

/**
 * Ends the session. Returns the URL to open at top level: the identity
 * provider's sign-out on cloud, the web app on OSS. A script cannot follow a
 * cross-origin sign-out redirect, so the backend answers a POST with the URL.
 */
export async function signOut(): Promise<string> {
  const { data } = await http.post<{ redirect_url: string }>("/api/v1/logout");
  return data.redirect_url;
}
