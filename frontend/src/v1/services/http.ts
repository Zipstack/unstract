import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  isCancel,
} from "axios";
import { expireSession } from "./context";
import { REQUEST_ID_HEADER, toApiError } from "./errors";

// The one HTTP client for v1; only services/ imports it (see README.md).

const CSRF_COOKIE = "csrftoken";
const CSRF_HEADER = "X-CSRFToken";
const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

/** Options every service function takes. */
export type RequestOptions = Readonly<{ signal?: AbortSignal }>;

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

/* A v4 UUID; randomUUID exists only in secure contexts (not plain-http on-prem). */
function newRequestId(): string {
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

// The CSRF token never goes to another origin.
const isSameOrigin = (url: string | undefined): boolean =>
  new URL(url ?? "", window.location.href).origin === window.location.origin;

function addHeaders(
  config: InternalAxiosRequestConfig,
): InternalAxiosRequestConfig {
  if (!config.headers.has(REQUEST_ID_HEADER)) {
    config.headers.set(REQUEST_ID_HEADER, newRequestId());
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

/** A client with its own session-expiry latch; services use `http`. */
export function createHttpClient(): AxiosInstance {
  const client = axios.create();
  let expired = false;
  client.interceptors.request.use(addHeaders);
  client.interceptors.response.use(undefined, (error: unknown) => {
    if (isCancel(error)) {
      return Promise.reject(error);
    }
    const apiError = toApiError(error);
    // Concurrent 401s redirect once.
    if (apiError.kind === "unauthenticated" && !expired) {
      expired = true;
      expireSession();
    }
    return Promise.reject(apiError);
  });
  return client;
}

export const http: AxiosInstance = createHttpClient();
