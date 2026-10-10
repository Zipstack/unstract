import Cookies from "js-cookie";

import { useSessionStore } from "../store/session-store";

const CSRF_HEADER = "X-CSRFToken";
const CSRF_COOKIE = "csrftoken";
const SAFE_METHODS = new Set(["get", "head", "options", "trace"]);

// Session store first; the cookie covers the bootstrap calls that run before
// the session is hydrated (org selection, session validation).
const getCsrfToken = () =>
  useSessionStore.getState().sessionDetails?.csrfToken ||
  Cookies.get(CSRF_COOKIE);

// The token must never leave our origin, so absolute URLs to other hosts are
// skipped.
const isSameOrigin = (url) => {
  if (!url) {
    return true;
  }
  try {
    const origin = globalThis.location?.origin;
    return new URL(url, origin).origin === origin;
  } catch {
    return false;
  }
};

// Same rule as axios' isAbsoluteURL: a scheme or protocol-relative `//host`.
const ABSOLUTE_URL = /^([a-z][a-z\d+\-.]*:)?\/\//i;

// Where axios will actually send the request: `baseURL` decides the origin
// unless the request URL is itself absolute.
const requestTarget = ({ url, baseURL }) =>
  baseURL && !ABSOLUTE_URL.test(url ?? "") ? baseURL : url;

const isUnsafeMethod = (method) =>
  !SAFE_METHODS.has((method || "get").toLowerCase());

const setHeaderIfMissing = (headers, value) => {
  if (typeof headers.set === "function") {
    headers.set(CSRF_HEADER, value, false);
    return;
  }
  if (!headers[CSRF_HEADER]) {
    headers[CSRF_HEADER] = value;
  }
};

const attachCsrfInterceptor = (axiosInstance) => {
  return axiosInstance.interceptors.request.use((config) => {
    if (
      !isUnsafeMethod(config.method) ||
      !isSameOrigin(requestTarget(config))
    ) {
      return config;
    }
    const token = getCsrfToken();
    if (token) {
      config.headers ??= {};
      setHeaderIfMissing(config.headers, token);
    }
    return config;
  });
};

const GLOBAL_INSTALL_FLAG = Symbol.for("unstract.csrfInterceptor");

// For the global axios default, which the few intentional raw-axios callers
// use. Idempotent, since App.jsx can be re-evaluated by HMR.
const installGlobalCsrfInterceptor = (axiosInstance) => {
  if (axiosInstance[GLOBAL_INSTALL_FLAG]) {
    return;
  }
  attachCsrfInterceptor(axiosInstance);
  axiosInstance[GLOBAL_INSTALL_FLAG] = true;
};

// For transports that bypass axios (e.g. the Upload shim's `action` fetch).
const getCsrfHeaders = () => {
  const token = getCsrfToken();
  return token ? { [CSRF_HEADER]: token } : {};
};

export {
  attachCsrfInterceptor,
  CSRF_HEADER,
  getCsrfHeaders,
  getCsrfToken,
  installGlobalCsrfInterceptor,
};
