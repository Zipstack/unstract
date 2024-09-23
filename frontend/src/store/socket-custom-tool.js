import { create } from "zustand";

const defaultState = {
  messages: [],
};

const STORE_VARIABLES = defaultState;

const useSocketCustomToolStore = create((setState, getState) => ({
  ...STORE_VARIABLES,
  updateCusToolMessages: (messages) => {
    const existingState = { ...getState() };
    let data = [...(existingState?.messages || []), ...messages];

    // Remove the previous messages if the length exceeds 200
    const dataLength = data?.length;
    if (dataLength > 200) {
      const index = dataLength - 200;
      data = data.slice(index);
    }

    existingState.messages = data;
    setState(existingState);
  },
  emptyCusToolMessages: () => {
    setState(defaultState);
  },
}));

export { useSocketCustomToolStore };
