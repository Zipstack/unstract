import { create } from "zustand";

import axios from "axios";
import { useSessionStore } from "./session-store";
import { useAlertStore } from "./alert-store";

const STORE_VARIABLES = {
  logs: [],
  blink: false,
};

const useSocketLogsStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  pushLogMessages: (msg) => {
    const existingState = { ...getState() };
    const { sessionDetails } = useSessionStore.getState();
    const { setAlertDetails } = useAlertStore.getState();
    let logsData = [...(existingState?.logs || [])];

    const newLog = {
      timestamp: Math.floor(Date.now() / 1000),
      key: logsData?.length + 1,
      level: msg?.level,
      stage: msg?.stage,
      step: msg?.step,
      state: msg?.state,
      prompt_key: msg?.component?.prompt_key,
      doc_name: msg?.component?.doc_name,
      message: msg?.message,
      cost_value: msg?.cost,
      iteration: msg?.iteration,
      iteration_total: msg?.iteration_total,
      type: msg?.type,
    };

    logsData.push(newLog);
    let blink = false;
    if (newLog?.type === "LOG" && newLog?.level === "ERROR") {
      setAlertDetails({
        type: "ERROR_LOG",
        message: newLog?.message,
      });
      blink = true;
    }
    if (newLog?.type === "NOTIFICATION" && sessionDetails?.isLoggedIn) {
      const requestOptions = {
        method: "POST",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/logs/`,
        headers: {
          "X-CSRFToken": sessionDetails?.csrfToken,
        },
        data: { log: JSON.stringify(newLog) },
      };
      axios(requestOptions).catch((err) => {});
    }
    // Remove the previous logs if the length exceeds 200
    const logsDataLength = logsData?.length;
    if (logsDataLength > 200) {
      const index = logsDataLength - 200;
      logsData = logsData.slice(index);
    }

    const result = {
      logs: logsData,
      blink,
    };
    setState({ ...existingState, ...result });
  },
  updateBlink: (value) => {
    const existingState = { ...getState() };
    setState({ ...existingState, ...{ blink: value } });
  },
  emptyLogs: () => {
    setState({ logs: [] });
  },
}));

export { useSocketLogsStore };
