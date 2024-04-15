import axios from "axios";
import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";

const userSession = async () => {
  try {
    const requestOptions = {
      method: "GET",
      url: "/api/v1/session",
    };
    console.log("requestOptions", requestOptions);
    const res = await axios(requestOptions);
    console.log("res", res);
    return res.data;
  } catch (error) {
    const handleException = useExceptionHandler();
    handleException(error, "Error while getting session");
  }
};

export { userSession };
