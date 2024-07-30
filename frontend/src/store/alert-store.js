import { create } from "zustand";
import { isNonNegativeNumber } from "../helpers/GetStaticData";
import { useSocketLogsStore } from "../store/socket-logs-store";
import { uniqueId } from "lodash";

const DEFAULT_DURATION = 6;

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
    if (details.type === "ERROR_LOG") {
      setState({
        alertDetails: {
          content: details.message,
          title: "Failed",
          duration: DEFAULT_DURATION,
          key: `open${Date.now()}-${uniqueId()}`,
          type: "error",
        },
      });
      return;
    }
    const { pushLogMessages } = useSocketLogsStore.getState();
    const isErrorType = details?.type === "error";
    const updatedDetails = {
      ...details,
      title: details.title || (isErrorType ? "Failed" : "Success"),
      duration: isNonNegativeNumber(details.duration)
        ? details.duration
        : DEFAULT_DURATION,
      key: `open${Date.now()}-${uniqueId()}`,
    };

    pushLogMessages({
      level: isErrorType ? "ERROR" : "SUCCESS",
      message: updatedDetails.content,
      type: "NOTIFICATION",
    });

    setState({ alertDetails: updatedDetails });
  },
}));

export { useAlertStore };
