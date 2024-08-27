import { useNavigate, useLocation } from "react-router-dom";
import PropTypes from "prop-types";

const useExceptionHandler = () => {
  const navigate = useNavigate();
  const location = useLocation();
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

    if (err?.response?.data) {
      const { type, errors } = err.response.data;
      switch (type) {
        case "validation_error":
          // Handle validation errors
          if (setBackendErrors) {
            setBackendErrors(err?.response?.data);
          } else {
            return {
              title: title,
              type: "error",
              content: errors?.[0]?.detail ? errors[0].detail : errMessage,
              duration: duration,
            };
          }
          break;
        case "subscription_error":
          if (location?.pathname === "/plans") {
            return;
          }
          navigate("/trial-expired");
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
