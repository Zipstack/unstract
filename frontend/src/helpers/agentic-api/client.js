import axios from "axios";

import { useAlertStore } from "../../store/alert-store";
import { useSessionStore } from "../../store/session-store";

// Construct API base URL with organization ID from session
const getApiBaseUrl = () => {
  const { sessionDetails } = useSessionStore.getState();
  const orgId = sessionDetails?.orgId || "";
  return `/api/v1/unstract/${orgId}/agentic`;
};

export const agenticApiClient = axios.create({
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

// Request interceptor to set baseURL dynamically and add CSRF token
agenticApiClient.interceptors.request.use(
  (config) => {
    // Set baseURL dynamically to include current org ID from session
    config.baseURL = getApiBaseUrl();

    const { sessionDetails } = useSessionStore.getState();
    if (sessionDetails?.csrfToken) {
      config.headers["X-CSRFToken"] = sessionDetails.csrfToken;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
agenticApiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Redirect to login on unauthorized
      window.location.href = "/landing";
    }
    return Promise.reject(error);
  }
);

export const handleApiError = (error) => {
  if (axios.isAxiosError(error)) {
    const apiError = error.response?.data;
    return apiError?.detail || apiError?.error || error.message;
  }
  return "An unexpected error occurred";
};

// Helper to show error notifications
export const showApiError = (error, customMessage = null) => {
  const { setAlertDetails } = useAlertStore.getState();
  const errorMessage = customMessage || handleApiError(error);

  setAlertDetails({
    type: "error",
    content: errorMessage,
    title: "Error",
    duration: 5,
    key: Date.now(),
  });
};

// Helper to show success notifications
export const showApiSuccess = (message, title = "Success") => {
  const { setAlertDetails } = useAlertStore.getState();

  setAlertDetails({
    type: "success",
    content: message,
    title,
    duration: 3,
    key: Date.now(),
  });
};
