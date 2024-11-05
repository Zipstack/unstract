import { create } from "zustand";

const defaultState = {
  activeApis: 0,
  queue: [],
};

const STORE_VARIABLES = { ...defaultState };

const usePromptRunQueueStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  setDefaultPromptRunQueue: () => {
    setState({ ...defaultState });
  },
  setPromptRunQueue: (promptRunQueueState) => {
    setState(promptRunQueueState);
  },
  pushPromptRunApi: (promptRunApiDetails) => {
    const existingState = { ...getState() };
    const newQueue = [...(existingState?.queue || []), ...promptRunApiDetails];
    setState({ existingState, ...{ queue: newQueue } });
  },
  freeActiveApi: (numOfApis = 1) => {
    const existingState = { ...getState() };
    const newActiveApis = existingState?.activeApis - numOfApis;

    if (newActiveApis < 0) return;

    setState({ ...existingState, ...{ activeApis: newActiveApis } });
  },
  removePromptRunApi: () => {
    const existingState = { ...getState() };
    const newActiveApis = existingState?.activeApis;
    const newQueue = [...(existingState?.queue || [])];
    if (!newQueue?.length) {
      return;
    }
    newQueue.shift();
    setState({ activeApis: newActiveApis - 1, queue: newQueue });
  },
}));

export { usePromptRunQueueStore };
