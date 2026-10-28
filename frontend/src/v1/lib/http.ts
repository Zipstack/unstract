import axios from "axios";

const SAFE_METHODS = new Set(["get", "head", "options"]);

function cookie(name: string): string | undefined {
  const prefix = `${name}=`;
  const entry = document.cookie
    .split("; ")
    .find((part) => part.startsWith(prefix));
  if (entry === undefined) {
    return undefined;
  }
  try {
    return decodeURIComponent(entry.slice(prefix.length));
  } catch {
    // A malformed value is no token: send no header and let the server refuse.
    return undefined;
  }
}

/**
 * The one HTTP client v1 services use. Django's session cookie authenticates;
 * unsafe methods carry the CSRF cookie back as X-CSRFToken. Set here rather
 * than through axios's xsrf options, which only the browser adapter applies.
 * ponytail: no 401 or error-toast handling yet; add it when a page needs it.
 */
export const http = axios.create({ withCredentials: true });

http.interceptors.request.use((config) => {
  const token = cookie("csrftoken");
  if (
    token !== undefined &&
    !SAFE_METHODS.has((config.method ?? "get").toLowerCase())
  ) {
    config.headers.set("X-CSRFToken", token);
  }
  return config;
});
