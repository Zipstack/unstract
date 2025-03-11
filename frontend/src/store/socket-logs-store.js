import { create } from "zustand";

import { useSessionStore } from "./session-store";
import axios from "axios";

const STORE_VARIABLES = {
  logs: [],
};

const useSocketLogsStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  pushLogMessages: (messages, isStoreNotifications = true) => {
    const existingState = { ...getState() };
    const { sessionDetails } = useSessionStore.getState();
    let logsData = [...(existingState?.logs || [])];

    const newLogs = messages.map((msg, index) => ({
      timestamp: msg?.timestamp,
      key: logsData?.length + index + 1,
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
    }));

    logsData = [...logsData, ...newLogs];

    newLogs.forEach((newLog) => {
      if (
        newLog?.type === "NOTIFICATION" &&
        sessionDetails?.isLoggedIn &&
        isStoreNotifications
      ) {
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
    });

    // Remove the previous logs if the length exceeds 1000
    const logsDataLength = logsData?.length;
    if (logsDataLength > 1000) {
      const index = logsDataLength - 1000;
      logsData = logsData.slice(index);
    }

    existingState.logs = logsData;

    setState(existingState);
  },
  emptyLogs: () => {
    setState({ logs: [] });
  },
}));

export { useSocketLogsStore };
