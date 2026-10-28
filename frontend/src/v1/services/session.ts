import { http } from "@v1/lib/http";
import posthog from "posthog-js";

/**
 * Ends the session. Returns the URL to open at top level: the identity
 * provider's sign-out on cloud, the web app on OSS. A script cannot follow a
 * cross-origin sign-out redirect, so the backend answers a POST with the URL.
 */
export async function signOut(): Promise<string> {
  const { data } = await http.post<{ redirect_url?: unknown }>(
    "/api/v1/logout",
  );
  if (typeof data?.redirect_url !== "string" || data.redirect_url === "") {
    throw new Error("Sign-out reply carried no redirect URL");
  }
  return data.redirect_url;
}

/** Signs out, forgets the analytics identity and leaves the app. */
export async function signOutAndLeave(): Promise<void> {
  let destination: string;
  try {
    destination = await signOut();
  } catch {
    // The GET logout ends the session too and redirects itself (v0's path).
    destination = "/api/v1/logout";
  }
  posthog.reset();
  window.location.assign(destination);
}
