import { onSignedOutElsewhere } from "@v1/lib/browserStorage";

/** POST answers with the sign-out URL; GET ends the session and redirects (v0's path). */
export const LOGOUT_PATH = "/api/v1/logout";

/**
 * When another tab signs out, signs this tab out through the GET logout, as
 * v0 does (see onSignedOutElsewhere). Mount once at the app root. When the
 * backend drops GET logout, move this to the POST too, without announcing the
 * sign-out again. It loads no HTTP client, so v0 can import it through `@v1`.
 */
export function signOutWhenSignedOutElsewhere(
  isSignedOut?: () => boolean,
): () => void {
  return onSignedOutElsewhere(
    () => window.location.assign(LOGOUT_PATH),
    isSignedOut,
  );
}
