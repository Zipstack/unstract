import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

let getTrialDetails;
try {
  getTrialDetails = require("../plugins/subscription/trial-helper/fetchTrialDetails.jsx");
} catch (err) {
  // Plugin not available
}

const useExceptionHandler = () => {
  const navigate = useNavigate();
  const handleException = (err, errMessage = "Something went wrong") => {
    if (!err) {
      return {
        type: "error",
        content: errMessage,
      };
    }

    if (err.response && err.response.data) {
      const { type, errors } = err.response.data;
      switch (type) {
        case "validation_error":
          // Handle validation errors
          break;
        case "subscription_error":
          if (getTrialDetails) {
            navigate("/trial-expired");
          }
          return {
            type: "error",
            content:
              errors && errors[0]?.detail ? errors[0].detail : errMessage,
          };
        case "client_error":
        case "server_error":
          return {
            type: "error",
            content:
              errors && errors[0]?.detail ? errors[0].detail : errMessage,
          };
        default:
          return {
            type: "error",
            content: errMessage,
          };
      }
    } else {
      return {
        type: "error",
        content: errMessage,
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
