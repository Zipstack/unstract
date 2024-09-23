import { create } from "zustand";

const defaultState = {
  promptOutputs: {},
};
const STORE_VARIABLES = { ...defaultState };

const usePromptOutputStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  resetPromptOutput: () => {
    setState(defaultState);
  },
  setPromptOutput: (outputs) => {
    setState({ promptOutputs: outputs });
  },
  updatePromptOutput: (outputs) => {
    const existingState = { ...getState() };
    let promptOutputs = existingState["promptOutputs"];
    promptOutputs = { ...promptOutputs, ...outputs };
    setState({ promptOutputs });
  },
  deletePromptOutput: (key) => {
    const existingState = { ...getState() };
    const promptOutputs = existingState["promptOutputs"];
    delete promptOutputs[key];
    setState({ promptOutputs });
  },
}));

export { usePromptOutputStore };
