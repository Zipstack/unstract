import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

const useExceptionHandler = () => {
  const navigate = useNavigate();
  const handleException = (
    err,
    errMessage = "Something went wrong",
    setBackendErrors = undefined,
    title = "Failed",
    duration = 0
  ) => {
    if (!err) {
      return {
        type: "error",
        content: errMessage,
        title: title,
        duration: duration,
      };
    }
    if (err.code === "ERR_NETWORK" && !navigator.onLine) {
      return {
        type: "error",
        content: "Please check your internet connection.",
        title: title,
        duration: duration,
      };
    } else if (err.code === "ERR_CANCELED") {
      return {
        type: "error",
        content: "Request has been canceled.",
        title: title,
        duration: duration,
      };
    }

    if (err?.response?.data) {
      const { type, errors } = err.response.data;
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
                        }`
                    )
                    .join("\n");
              }
            }
            return {
              title: title,
              type: "error",
              content: errorMessage,
              duration: duration,
            };
          }
          break;
        case "subscription_error":
          navigate("/subscription-expired");
          return {
            title: title,
            type: "error",
            content: errors,
            duration: duration,
          };
        case "client_error":
        case "server_error":
          return {
            title: title,
            type: "error",
            content: errors?.[0]?.detail ? errors[0].detail : errMessage,
            duration: duration,
          };
        default:
          return {
            title: title,
            type: "error",
            content: errMessage,
            duration: duration,
          };
      }
    } else {
      return {
        title: title,
        type: "error",
        content: errMessage,
        duration: duration,
      };
    }
  };

  return handleException;
};

useExceptionHandler.propTypes = {
  err: PropTypes.object, // Assuming err is an object
  errMessage: PropTypes.string,
};

export { useExceptionHandler };
