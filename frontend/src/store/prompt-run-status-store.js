import { create } from "zustand";

const STORE_VARIABLES = {
  promptRunStatus: {},
};

const usePromptRunStatusStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  clearPromptStatus: () => {
    setState({ promptRunStatus: {} });
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
