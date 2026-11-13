import posthog from "posthog-js";
import { http, type RequestOptions } from "./http";

/**
 * Ends the session. Returns the URL to open at top level: the identity
 * provider's sign-out on cloud, the web app on OSS. A script cannot follow a
 * cross-origin sign-out redirect, so the backend answers a POST with the URL.
 */
export async function signOut({
  signal,
}: Pick<RequestOptions, "signal"> = {}): Promise<string> {
  const { data } = await http.post<{ redirect_url?: unknown }>(
    "/api/v1/logout",
    undefined,
    { signal },
  );
  if (typeof data?.redirect_url !== "string" || data.redirect_url === "") {
    throw new Error("Sign-out reply carried no redirect URL");
  }
  const url = new URL(data.redirect_url, window.location.origin);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("Sign-out reply carried a non-http redirect URL");
  }
  return url.href;
}

/** Signs out, forgets the analytics identity and leaves the app. */
export async function signOutAndLeave(): Promise<void> {
  let destination: string;
  try {
    destination = await signOut();
  } catch (error) {
    // Logged so a failing POST shows up: the backend drops GET logout once v0 goes.
    console.error("Sign-out POST failed; falling back to GET", error);
    // The GET logout ends the session too and redirects itself (v0's path).
    destination = "/api/v1/logout";
  }
  posthog.reset();
  window.location.assign(destination);
}
