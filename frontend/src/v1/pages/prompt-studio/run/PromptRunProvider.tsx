import { useQueryClient } from "@tanstack/react-query";
import { promptRunStore, type RunStore } from "@v1/stores/promptRuns";
import {
  createContext,
  type JSX,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import type { RunChannel } from "./channel";
import { createRunEngine, type RunEngine, refreshToolOutputs } from "./engine";
import { isToolRunning } from "./summary";

const RunEngineContext = createContext<RunEngine | null>(null);

export type PromptRunProviderProps = Readonly<{
  /** The real-time channel's subscription. */
  channel: RunChannel;
  children: ReactNode;
  /** The app's store unless a test passes its own. */
  store?: RunStore;
}>;

/**
 * Runs the engine for everything below it. Mount it above the Prompt Studio
 * routes (where v0 mounts its run listener for the whole signed-in app), so
 * a run keeps going and its results land while the user is elsewhere.
 */
export function PromptRunProvider({
  channel,
  children,
  store = promptRunStore,
}: PromptRunProviderProps): JSX.Element {
  const queryClient = useQueryClient();
  const [engine, setEngine] = useState<RunEngine | null>(null);
  useEffect(() => {
    const next = createRunEngine({ store, channel, queryClient });
    setEngine(next);
    return () => {
      next.dispose();
      setEngine(null);
    };
  }, [store, channel, queryClient]);
  return (
    <RunEngineContext.Provider value={engine}>
      {children}
    </RunEngineContext.Provider>
  );
}

/** Run and single-pass actions; null until the engine has mounted. */
export function usePromptRunActions(): RunEngine | null {
  return useContext(RunEngineContext);
}

/**
 * For the workspace: on mount during a run of this tool, refetch its outputs,
 * so returning to the project shows the latest state from the server.
 */
export function useRefreshOutputsOnReturn(
  toolId: string,
  store: RunStore = promptRunStore,
): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (isToolRunning(store.getState(), toolId)) {
      void refreshToolOutputs(queryClient, toolId);
    }
  }, [queryClient, store, toolId]);
}
