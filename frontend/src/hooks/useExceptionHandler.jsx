import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";

import { useSessionStore } from "../store/session-store.js";

const useExceptionHandler = () => {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();

  // Resolves relative markdown links [text](/path) to [text](/{orgName}/path)
  const enrichMarkdownLinks = (message) => {
    if (typeof message !== "string") {
      return message;
    }
    const orgName = sessionDetails?.orgName;
    if (!orgName) {
      return message;
    }
    return message.replace(
      /\[([^\]]+)\]\(\/((?!\/)[^)]+)\)/g,
      (_, text, path) => `[${text}](/${orgName}/${path})`,
    );
  };

  const buildAlert = (content, title, duration) => ({
    type: "error",
    content: enrichMarkdownLinks(content),
    title,
    duration,
  });

  const handleException = (
    err,
    errMessage = "Something went wrong",
    setBackendErrors = undefined,
    title = "Failed",
    duration = 0,
  ) => {
    if (!err) {
      return buildAlert(errMessage, title, duration);
    }
    if (err.code === "ERR_NETWORK" && !navigator.onLine) {
      return buildAlert(
        "Please check your internet connection.",
        title,
        duration,
      );
    } else if (err.code === "ERR_CANCELED") {
      return buildAlert("Request has been canceled.", title, duration);
    }

    if (err?.response?.data) {
      const responseData = err.response.data;
      const { type, errors } = responseData;

      // First, try to extract common API error messages (for DRF and other APIs)
      const commonErrorMessage =
        responseData.error || responseData.detail || responseData.message;

      if (commonErrorMessage) {
        return buildAlert(commonErrorMessage, title, duration);
      }

      // Then handle specific error types
      switch (type) {
        case "validation_error":
          // Handle validation errors
          if (setBackendErrors) {
            setBackendErrors(err?.response?.data);
          } else {
            // Handle both single error and array of errors
            let errorMessage = "Validation error";
            if (errors && Array.isArray(errors) && errors.length > 0) {
              if (errors.length === 1) {
                // Single error
                const error = errors[0];
                errorMessage = error.attr
                  ? `${error.attr}: ${error.detail}`
                  : error.detail || errMessage;
              } else {
                // Multiple errors - format as list
                errorMessage =
                  "Validation errors:\n" +
                  errors
                    .map(
                      (error) =>
                        `• ${error.attr ? error.attr + ": " : ""}${
                          error.detail || "Unknown error"
                        }`,
                    )
                    .join("\n");
              }
            }
            return buildAlert(errorMessage, title, duration);
          }
          break;
        case "subscription_error":
          navigate("/subscription-expired");
          return buildAlert(errors, title, duration);
        case "client_error":
        case "server_error":
          return buildAlert(
            errors?.[0]?.detail ? errors[0].detail : errMessage,
            title,
            duration,
          );
        default:
          return buildAlert(errMessage, title, duration);
      }
    } else {
      return buildAlert(errMessage, title, duration);
    }
  };

  return handleException;
};

useExceptionHandler.propTypes = {
  err: PropTypes.object, // Assuming err is an object
  errMessage: PropTypes.string,
};

export { useExceptionHandler };
