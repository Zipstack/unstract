import { v4 as uuidv4 } from "uuid";

const REQUEST_ID_HEADER = "X-Request-ID";

const attachRequestIdInterceptor = (axiosInstance) => {
  return axiosInstance.interceptors.request.use((config) => {
    if (!config.headers[REQUEST_ID_HEADER]) {
      config.headers[REQUEST_ID_HEADER] = uuidv4();
    }
    return config;
  });
};

const getRequestIdFromError = (err) => {
  return (
    err?.response?.headers?.[REQUEST_ID_HEADER.toLowerCase()] ||
    err?.response?.headers?.[REQUEST_ID_HEADER] ||
    err?.config?.headers?.[REQUEST_ID_HEADER]
  );
};

export { REQUEST_ID_HEADER, attachRequestIdInterceptor, getRequestIdFromError };
