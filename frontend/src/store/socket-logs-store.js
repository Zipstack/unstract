import { create } from "zustand";

import { getTimeForLogs } from "../helpers/GetStaticData";

const STORE_VARIABLES = {
  logs: [],
};

const useSocketLogsStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  pushLogMessages: (msg) => {
    const existingState = { ...getState() };
    let logsData = [...(existingState?.logs || [])];

    const newLog = {
      timestamp: getTimeForLogs(),
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
    };

    logsData.push(newLog);

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
