import { create } from "zustand";
import { uniqueId } from "lodash";

import { isNonNegativeNumber } from "../helpers/GetStaticData";

const DEFAULT_DURATION = 6;
const SUCCESS_DURATION = 2;

const STORE_VARIABLES = {
  alertDetails: {
    type: "",
    content: "",
    title: "",
    duration: DEFAULT_DURATION,
    key: null,
  },
};

const useAlertStore = create((setState) => ({
  ...STORE_VARIABLES,
  setAlertDetails: (details) => {
    if (!details) return STORE_VARIABLES;

    const isErrorType = details?.type === "error";
    const isSuccessType = details?.type === "success";
    const defaultDuration = isSuccessType ? SUCCESS_DURATION : DEFAULT_DURATION;
    const updatedDetails = {
      ...details,
      title: details.title || (isErrorType ? "Failed" : "Success"),
      duration: isNonNegativeNumber(details.duration)
        ? details.duration
        : defaultDuration,
      key: `open${Date.now()}-${uniqueId()}`,
    };

    setState({ alertDetails: updatedDetails });
  },
}));

export { useAlertStore };
