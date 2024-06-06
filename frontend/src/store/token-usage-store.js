import { create } from "zustand";

const STORE_VARIABLES = {
  tokenUsage: {},
};

const useTokenUsageStore = create((setState) => ({
  ...STORE_VARIABLES,
  setTokenUsage: (tokenUsageId, data) => {
    setState((state) => ({
      tokenUsage: {
        ...state.tokenUsage,
        [tokenUsageId]: data,
      },
    }));
  },
  resetTokenUsage: () => {
    setState(STORE_VARIABLES);
  },
}));

export { useTokenUsageStore };
