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

    if (newActiveApis < 0) {
      return;
    }

    setState({ ...existingState, ...{ activeApis: newActiveApis } });
  },
  // Drop queued-but-not-yet-sent runs. `activeApis` is deliberately untouched:
  // it counts requests already in flight, which a queue purge cannot recall —
  // decrementing it here would let the pump start more work than allowed
  // (UN-1031).
  removeQueuedApis: (shouldRemove) => {
    const existingState = { ...getState() };
    const queue = existingState?.queue || [];
    const removed = queue.filter((api) => shouldRemove(api));
    if (!removed.length) {
      return [];
    }
    setState({
      ...existingState,
      queue: queue.filter((api) => !shouldRemove(api)),
    });
    return removed;
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
