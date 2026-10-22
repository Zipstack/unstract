import axios from "axios";
import { create } from "zustand";

import { orgApi } from "../helpers/orgApi";
import { useSessionStore } from "./session-store";

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
      message: msg?.message || msg?.log,
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
          url: orgApi("logs/"),
          data: { log: JSON.stringify(newLog) },
        };
        // Raw axios on purpose: a store cannot use hooks, and a failed
        // background log write must not log the user out. CSRF comes from the
        // global interceptor in App.jsx.
        axios(requestOptions).catch((err) => {
          // Best-effort persistence, but leave a trace instead of failing
          // silently.
          console.warn("[socket-logs-store] Failed to persist notification", {
            status: err?.response?.status,
            message: err?.message,
          });
        });
      }
    });

    // Remove the previous logs if the length exceeds 200
    const logsDataLength = logsData?.length;
    if (logsDataLength > 200) {
      const index = logsDataLength - 200;
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
