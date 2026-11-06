/*
 * RequireAuth sends a signed-out visitor to /landing with the page they asked
 * for in router state under this key. The login link passes that page to
 * `/api/v1/login` as `redirect_url`, so the sign-in ends where it started.
 * The backend validates `redirect_url` again before redirecting.
 */
const LOGIN_FROM_STATE_KEY = "from";
const REDIRECT_URL_PARAM = "redirect_url";

/*
 * The path and query of `from` (a router location), or null when it is not a
 * same-origin path worth returning to. Only a single leading `/` is accepted:
 * `//host` and `/\host` resolve to another origin, and anything with a scheme
 * is not a path.
 */
function getPostLoginPath(from) {
  const pathname = from?.pathname;
  if (
    typeof pathname !== "string" ||
    !pathname.startsWith("/") ||
    pathname.startsWith("//") ||
    pathname.startsWith("/\\") ||
    pathname === "/"
  ) {
    return null;
  }
  const search =
    typeof from?.search === "string" && from.search.startsWith("?")
      ? from.search
      : "";
  const path = `${pathname}${search}`;
  try {
    const origin = window.location.origin;
    if (new URL(path, origin).origin !== origin) {
      return null;
    }
  } catch {
    return null;
  }
  return path;
}

export { getPostLoginPath, LOGIN_FROM_STATE_KEY, REDIRECT_URL_PARAM };
