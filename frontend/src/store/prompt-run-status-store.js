import { create } from "zustand";

const STORE_VARIABLES = {
  promptRunStatus: {},
  // In-flight runs, keyed by the run_id sent with the POST. The spinner map
  // above says *what* is running; this says *which backend run* is running it,
  // which is what a Stop needs in order to name the run to cancel (UN-1031).
  // Entries are added before the POST is sent, so a Stop works even while the
  // request is still blocked in the backend's extract/index stages.
  activeRuns: {},
};

const usePromptRunStatusStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  clearPromptStatus: () => {
    setState({ promptRunStatus: {} });
  },
  registerRun: (runId, runDetails) => {
    if (!runId) {
      return;
    }
    setState((state) => ({
      activeRuns: {
        ...state.activeRuns,
        [runId]: { ...runDetails, stopping: false, stoppingPromptIds: [] },
      },
    }));
  },
  // `promptIds` narrows the mark to the prompts actually being stopped. A
  // bulk run covers many prompts, and stopping one must not make the others
  // look like they are stopping too — their work carries on, and their Stop
  // buttons have to keep working (UN-1031). Omit it to mark the whole run.
  markRunsStopping: (runIds, promptIds) => {
    setState((state) => {
      const activeRuns = { ...state.activeRuns };
      (runIds || []).forEach((runId) => {
        const run = activeRuns[runId];
        if (!run) {
          return;
        }
        const stoppingPromptIds = promptIds
          ? [...new Set([...(run.stoppingPromptIds || []), ...promptIds])]
          : run.promptIds || [];
        activeRuns[runId] = {
          ...run,
          stopping: true,
          stoppingPromptIds,
        };
      });
      return { activeRuns };
    });
  },
  // A Stop that the backend could not record leaves the run going, so the
  // "stopping" mark has to come back off — otherwise its Stop button stays
  // disabled forever and the user cannot retry.
  unmarkRunsStopping: (runIds) => {
    setState((state) => {
      const activeRuns = { ...state.activeRuns };
      (runIds || []).forEach((runId) => {
        if (activeRuns[runId]) {
          activeRuns[runId] = {
            ...activeRuns[runId],
            stopping: false,
            stoppingPromptIds: [],
          };
        }
      });
      return { activeRuns };
    });
  },
  unregisterRun: (runId) => {
    setState((state) => {
      if (!runId || !state.activeRuns[runId]) {
        return {};
      }
      const activeRuns = { ...state.activeRuns };
      delete activeRuns[runId];
      return { activeRuns };
    });
  },
  clearActiveRuns: () => {
    setState({ activeRuns: {} });
  },
  addPromptStatus: (promptStatus) => {
    setState((state) => {
      const currentStatus = state.promptRunStatus || {};
      const newStatus = { ...currentStatus };

      for (const promptId in promptStatus) {
        if (Object.hasOwn(promptStatus, promptId)) {
          newStatus[promptId] = {
            ...currentStatus[promptId],
            ...promptStatus[promptId],
          };
        }
      }

      return { promptRunStatus: newStatus };
    });
  },
  clearPromptStatusById: (promptId) => {
    setState((state) => {
      const newStatus = { ...state.promptRunStatus };
      delete newStatus[promptId];
      return { promptRunStatus: newStatus };
    });
  },
  removePromptStatus: (promptId, key) => {
    setState((state) => {
      const currentStatus = state.promptRunStatus || {};
      const newStatus = { ...currentStatus };

      if (Object.hasOwn(newStatus, promptId)) {
        const promptStatus = { ...newStatus[promptId] };
        delete promptStatus[key];

        if (Object.keys(promptStatus).length === 0) {
          delete newStatus[promptId];
        } else {
          newStatus[promptId] = promptStatus;
        }
      }

      return { promptRunStatus: newStatus };
    });
  },
}));

export { usePromptRunStatusStore };
