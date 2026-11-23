import { newUuid } from "@v1/lib/uuid";
import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  isCancel,
} from "axios";
import { currentOrganizationId, expireSession } from "./context";
import { REQUEST_ID_HEADER, toApiError } from "./errors";

// The one HTTP client for v1 and its backend paths; who may import it: src/v1/README.md (Data layer).

const CSRF_COOKIE = "csrftoken";
const CSRF_HEADER = "X-CSRFToken";
const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

/** Options every service function takes. */
export type RequestOptions = Readonly<{
  signal?: AbortSignal;
  /** The organisation to call; a query passes its key's, else the current one. */
  org?: string;
}>;

/** `/api/v1/unstract/<org>` + path, the trailing slash kept as written. */
export function orgPath(
  path: `/${string}`,
  org: string = currentOrganizationId(),
): string {
  return `/api/v1/unstract/${encodeURIComponent(org)}${path}`;
}

function readCookie(name: string): string | undefined {
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
    // A malformed value is no token: the backend refuses the request.
    return undefined;
  }
}

// The CSRF token never goes to another origin.
const isSameOrigin = (url: string | undefined): boolean =>
  new URL(url ?? "", window.location.href).origin === window.location.origin;

function addHeaders(
  config: InternalAxiosRequestConfig,
): InternalAxiosRequestConfig {
  if (!config.headers.has(REQUEST_ID_HEADER)) {
    config.headers.set(REQUEST_ID_HEADER, newUuid());
  }
  const method = (config.method ?? "get").toLowerCase();
  if (!MUTATING_METHODS.has(method) || !isSameOrigin(config.url)) {
    return config;
  }
  const token = readCookie(CSRF_COOKIE);
  if (token !== undefined) {
    config.headers.set(CSRF_HEADER, token);
  }
  return config;
}

export type HttpClientOptions = Readonly<{
  /** False for a call whose 401 means "signed out" rather than an expired session. Default true. */
  expiresSession?: boolean;
}>;

/** A client with its own session-expiry latch; services use `http`. */
export function createHttpClient({
  expiresSession = true,
}: HttpClientOptions = {}): AxiosInstance {
  const client = axios.create();
  let expired = false;
  client.interceptors.request.use(addHeaders);
  client.interceptors.response.use(undefined, (error: unknown) => {
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const apiError = toApiError(error);
    // Once per page load, so concurrent 401s redirect once; the handler leaves the page.
    if (expiresSession && apiError.kind === "unauthenticated" && !expired) {
      expired = true;
      expireSession();
    }
    return Promise.reject(apiError);
  });
  return client;
}

export const http: AxiosInstance = createHttpClient();
