import { create } from "zustand";

const STORE_VARIABLES = {
  tokenUsage: {},
};

const useTokenUsageStore = create((setState) => ({
  ...STORE_VARIABLES,
  setTokenUsage: (data) => {
    setState({
      tokenUsage: { ...data },
    });
  },
  updateTokenUsage: (data) => {
    setState((state) => ({
      tokenUsage: {
        ...state.tokenUsage,
        ...data,
      },
    }));
  },
  resetTokenUsage: () => {
    setState(STORE_VARIABLES);
  },
}));

export { useTokenUsageStore };
