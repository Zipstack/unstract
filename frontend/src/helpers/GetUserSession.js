import axios from "axios";
import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../store/alert-store";
const userSession = async () => {
  try {
    const requestOptions = {
      method: "GET",
      url: "/api/v1/session",
    };
    const res = await axios(requestOptions);
    return res.data;
  } catch (error) {
    const handleException = useExceptionHandler();
    const { setAlertDetails } = useAlertStore();
    setAlertDetails(handleException(error, "Error while getting session"));
  }
};

export { userSession };
