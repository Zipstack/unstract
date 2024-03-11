import { useNavigate } from "react-router-dom";

const useExceptionHandler = (err, errMessage) => {
  const navigate = useNavigate();

  if (err?.response?.data?.type === "validation_error") {
    // Handle validation errors
  } else if (err?.response?.data?.type === "subscription_error") {
    navigate("/trial");
    return {
      type: "error",
      content:
        err?.response?.data?.errors[0].detail ||
        errMessage ||
        "Something went wrong",
    };
  } else if (
    ["client_error", "server_error"].includes(err?.response?.data?.type)
  ) {
    // Handle client_error, server_error
    return {
      type: "error",
      content:
        err?.response?.data?.errors[0].detail ||
        errMessage ||
        "Something went wrong",
    };
  } else {
    return {
      type: "error",
      content: err?.message,
    };
  }
};

export { useExceptionHandler };
