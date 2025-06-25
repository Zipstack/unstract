import { create } from "zustand";

const STORE_VARIABLES = {
  count: 0,
  isLoading: false,
  error: null,
};

const usePromptStudioStore = create((set, get) => {
  return {
    ...STORE_VARIABLES,
    fetchCount: async (getPromptStudioCount) => {
      // Prevent duplicate calls if already loading or if we already have a count
      if (get().isLoading || (get().count > 0 && !get().error)) return;

      set({ isLoading: true });
      try {
        const count = await getPromptStudioCount();
        set({ count, isLoading: false, error: null });
      } catch (error) {
        set({ error, isLoading: false });
      }
    },
    resetStore: () => {
      set(STORE_VARIABLES);
    },
  };
});

export { usePromptStudioStore };
