import { create } from "zustand";
import { isNonNegativeNumber } from "../helpers/GetStaticData";

const STORE_VARIABLES = {
  alertDetails: {
    type: "",
    content: "",
    title: "",
    duration: undefined,
    key: null,
  },
};
const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    setState(() => {
      if (!details) return STORE_VARIABLES;
      const isErrorType = details?.type === "error";
      details["title"] = details?.title || (isErrorType ? "Failed" : "Success");
      details["duration"] = isNonNegativeNumber(details?.duration)
        ? details?.duration
        : isErrorType
        ? 0
        : undefined;
      details["key"] = `open${Date.now()}`;
      return { alertDetails: { ...details } };
    });
  },
}));

export { useAlertStore };
