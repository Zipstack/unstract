import { useCallback } from "react";

import { usePromptStudioService } from "../components/api/prompt-studio-service";
import { useRetrievalStrategiesStore } from "../store/retrieval-strategies-store";

const ICON_MAP = {
  SearchOutlined: "SearchOutlined",
  QuestionCircleOutlined: "QuestionCircleOutlined",
  ForkOutlined: "ForkOutlined",
  ReloadOutlined: "ReloadOutlined",
  ShareAltOutlined: "ShareAltOutlined",
  TableOutlined: "TableOutlined",
  MergeCellsOutlined: "MergeCellsOutlined",
};

export const useRetrievalStrategies = () => {
  const {
    strategies,
    isLoading,
    error,
    setStrategies,
    setLoading,
    setError,
    shouldFetch,
  } = useRetrievalStrategiesStore();

  const { getRetrievalStrategies } = usePromptStudioService();

  const fetchStrategies = useCallback(
    async (toolId) => {
      // Check if we need to fetch (not cached or cache expired)
      if (!shouldFetch()) {
        return strategies;
      }

      setLoading(true);

      try {
        const data = await getRetrievalStrategies(toolId);

        // Transform the backend data to match our frontend format
        const transformedStrategies = Object.values(data).map((strategy) => ({
          ...strategy,
          icon: ICON_MAP[strategy.icon] || "SearchOutlined",
          bestFor: strategy.best_for || [],
          tokenUsage: strategy.token_usage || "Unknown",
          costImpact: strategy.cost_impact || "Unknown",
          technicalDetails: strategy.technical_details || "",
        }));

        setStrategies(transformedStrategies);
        return transformedStrategies;
      } catch (error) {
        console.error("Error fetching retrieval strategies:", error);
        setError(error.message);

        // Don't return hardcoded fallback - let the calling component handle the error
        throw error;
      }
    },
    [
      shouldFetch,
      strategies,
      setStrategies,
      setLoading,
      setError,
      getRetrievalStrategies,
    ]
  );

  const getStrategies = useCallback(
    (toolId) => {
      // If we have cached strategies and they're not expired, return them immediately
      if (strategies && !shouldFetch()) {
        return Promise.resolve(strategies);
      }

      // Otherwise fetch from API
      return fetchStrategies(toolId);
    },
    [strategies, shouldFetch, fetchStrategies]
  );

  return {
    strategies,
    isLoading,
    error,
    getStrategies,
    fetchStrategies,
  };
};
