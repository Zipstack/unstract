import { create } from "zustand";
import { isNonNegativeNumber } from "../helpers/GetStaticData";

const STORE_VARIABLES = {
  alertDetails: {
    type: "",
    content: "",
    title: "",
    duration: undefined,
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      const isErrorType = details?.type === "error";
      details["title"] =
        details["title"] || (isErrorType ? "Failed" : "Success");
      details["duration"] = isNonNegativeNumber(details.duration)
        ? details.duration
        : isErrorType
        ? 0
        : undefined;
      return { alertDetails: { ...details } };
    });
  },
}));

export { useAlertStore };
