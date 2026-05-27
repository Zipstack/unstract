import { v4 as uuidv4 } from "uuid";

const REQUEST_ID_HEADER = "X-Request-ID";

const setHeaderIfMissing = (headers, value) => {
  if (typeof headers.set === "function") {
    headers.set(REQUEST_ID_HEADER, value, false);
    return;
  }
  if (!headers[REQUEST_ID_HEADER]) {
    headers[REQUEST_ID_HEADER] = value;
  }
};

const attachRequestIdInterceptor = (axiosInstance) => {
  return axiosInstance.interceptors.request.use((config) => {
    config.headers ??= {};
    setHeaderIfMissing(config.headers, uuidv4());
    return config;
  });
};

const getRequestIdFromError = (err) => {
  return (
    err?.response?.headers?.[REQUEST_ID_HEADER.toLowerCase()] ??
    err?.config?.headers?.[REQUEST_ID_HEADER]
  );
};

export { REQUEST_ID_HEADER, attachRequestIdInterceptor, getRequestIdFromError };
