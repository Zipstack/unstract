import { create } from "zustand";
import { promptStudioService } from "../components/api/prompt-studio-service";

const STORE_VARIABLES = {
  count: 0,
  isLoading: false,
  error: null,
};

const usePromptStudioStore = create((set, get) => {
  const promptStudioApiService = promptStudioService();

  return {
    ...STORE_VARIABLES,
    fetchCount: async () => {
      // Don't fetch if already loading
      if (get().isLoading) return;

      set({ isLoading: true });
      try {
        const count = await promptStudioApiService.getPromptStudioCount();
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
