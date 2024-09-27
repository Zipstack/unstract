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
    const existingState = { ...getState() };
    const newPromptStatus = {
      ...(existingState?.promptRunStatus || {}),
      ...promptStatus,
    };
    setState({ promptRunStatus: newPromptStatus });
  },
  removePromptStatus: (id) => {
    const existingState = { ...getState() };
    const newPromptStatus = { ...(existingState?.promptRunStatus || {}) };
    delete newPromptStatus[id];
    setState({ promptRunStatus: newPromptStatus });
  },
}));

export { usePromptRunStatusStore };
