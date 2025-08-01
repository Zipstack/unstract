import { create } from "zustand";

const defaultState = {
  strategies: null,
  isLoading: false,
  error: null,
  lastFetched: null,
};

const useRetrievalStrategiesStore = create((set, get) => ({
  ...defaultState,

  setStrategies: (strategies) =>
    set({
      strategies,
      isLoading: false,
      error: null,
      lastFetched: Date.now(),
    }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) =>
    set({
      error,
      isLoading: false,
    }),

  clearStrategies: () => set({ ...defaultState }),

  // Check if strategies need to be fetched (cache for 1 hour)
  shouldFetch: () => {
    const { strategies, lastFetched } = get();
    if (!strategies) return true;

    const oneHour = 60 * 60 * 1000; // 1 hour in milliseconds
    const now = Date.now();

    return !lastFetched || now - lastFetched > oneHour;
  },
}));

export { useRetrievalStrategiesStore };
