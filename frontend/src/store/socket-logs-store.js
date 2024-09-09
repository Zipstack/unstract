import { create } from "zustand";

import { getTimeForLogs } from "../helpers/GetStaticData";

const STORE_VARIABLES = {
  logs: [],
};

const useSocketLogsStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  pushLogMessages: (messages) => {
    const existingState = { ...getState() };
    let logsData = [...(existingState?.logs || [])];

    const newLogs = messages.map((msg, index) => ({
      timestamp: getTimeForLogs(),
      key: logsData?.length + index + 1,
      level: msg?.level,
      stage: msg?.stage,
      step: msg?.step,
      message: msg?.message,
      cost_type: msg?.cost_type,
      cost_units: msg?.cost_units,
      cost_value: msg?.cost,
      iteration: msg?.iteration,
      iteration_total: msg?.iteration_total,
    }));

    logsData = [...logsData, ...newLogs];

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
