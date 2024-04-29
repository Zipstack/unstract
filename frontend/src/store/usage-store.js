import { create } from "zustand";

const useUsageStore = create((setState) => ({
  llmTokenUsage: null,
  setLLMTokenUsage: (data) => {
    setState({ llmTokenUsage: data });
  },
}));

export { useUsageStore };
