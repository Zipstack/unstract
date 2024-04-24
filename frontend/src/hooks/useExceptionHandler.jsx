import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

const useExceptionHandler = () => {
  const navigate = useNavigate();
  const handleException = (
    err,
    errMessage = "Something went wrong",
    setBackendErrors = undefined,
    title = "Failed"
  ) => {
    if (!err) {
      return {
        type: "error",
        content: errMessage,
        title: title,
        duration: 0,
      };
    }

    if (err?.response && err?.response.data) {
      const { type, errors } = err.response.data;
      switch (type) {
        case "validation_error":
          // Handle validation errors
          if (setBackendErrors) {
            setBackendErrors(err?.response?.data);
          }
          break;
        case "subscription_error":
          navigate("/trial-expired");
          return {
            title: title,
            type: "error",
            content:
              errors && errors[0]?.detail ? errors[0].detail : errMessage,
            duration: 0,
          };
        case "client_error":
        case "server_error":
          return {
            title: title,
            type: "error",
            content:
              errors && errors[0]?.detail ? errors[0].detail : errMessage,
            duration: 0,
          };
        default:
          return {
            title: title,
            type: "error",
            content: errMessage,
            duration: 0,
          };
      }
    } else {
      return {
        title: title,
        type: "error",
        content: errMessage,
        duration: 0,
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
