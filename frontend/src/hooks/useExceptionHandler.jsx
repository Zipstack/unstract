import { useNavigate } from "react-router-dom";

import { getRequestIdFromError } from "../helpers/requestId";

const useExceptionHandler = () => {
  const navigate = useNavigate();

  const handleException = (
    err,
    errMessage = "Something went wrong",
    setBackendErrors = undefined,
    title = "Failed",
    duration = 0,
  ) => {
    const requestId = getRequestIdFromError(err) ?? null;
    const alert = (content) => ({
      type: "error",
      content,
      title,
      duration,
      requestId,
    });

    if (!err) {
      return alert(errMessage);
    }
    if (err.code === "ERR_NETWORK" && !navigator.onLine) {
      return alert("Please check your internet connection.");
    } else if (err.code === "ERR_CANCELED") {
      return alert("Request has been canceled.");
    }

    if (err?.response?.data) {
      const responseData = err.response.data;
      const { type, errors } = responseData;

      // First, try to extract common API error messages (for DRF and other APIs)
      const commonErrorMessage =
        responseData.error || responseData.detail || responseData.message;

      if (commonErrorMessage) {
        return alert(commonErrorMessage);
      }

      // Then handle specific error types
      switch (type) {
        case "validation_error":
          // Handle validation errors
          if (setBackendErrors) {
            setBackendErrors(err?.response?.data);
            // Field-bound errors render inline next to their input. Errors not
            // tied to a field (non_field_errors / attr-less) map to no input and
            // would otherwise vanish silently — surface them as a toast.
            const nonFieldErrors = (errors || []).filter(
              (error) => !error?.attr || error.attr === "non_field_errors",
            );
            if (nonFieldErrors.length > 0) {
              return alert(
                nonFieldErrors
                  .map((error) => error?.detail || errMessage)
                  .join("\n"),
              );
            }
            // No non-field errors: field-level errors are rendered inline.
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
            return alert(errorMessage);
          }
          break;
        case "subscription_error":
          navigate("/subscription-expired");
          return alert(errors);
        case "client_error":
        case "server_error":
          return alert(errors?.[0]?.detail ? errors[0].detail : errMessage);
        default:
          return alert(errMessage);
      }
    } else {
      return alert(errMessage);
    }
  };

  return handleException;
};

export { useExceptionHandler };
