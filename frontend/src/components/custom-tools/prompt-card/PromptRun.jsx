import { useEffect } from "react";
import Cookies from "js-cookie";
import { usePromptRunQueueStore } from "../../../store/prompt-run-queue-store";
import usePromptRun from "../../../hooks/usePromptRun";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";

const MAX_ACTIVE_APIS = 5;

function PromptRun() {
  const activeApis = usePromptRunQueueStore((state) => state.activeApis);
  const queue = usePromptRunQueueStore((state) => state.queue);
  const setPromptRunQueue = usePromptRunQueueStore(
    (state) => state.setPromptRunQueue
  );
  const { runPrompt, syncPromptRunApisAndStatus } = usePromptRun();
  const promptRunStatus = usePromptRunStatusStore(
    (state) => state.promptRunStatus
  );
  const updateCustomTool = useCustomToolStore(
    (state) => state.updateCustomTool
  );

  useEffect(() => {
    // Retrieve queue from cookies on component load
    const queueData = Cookies.get("promptRunQueue");
    if (queueData && JSON.parse(queueData)?.length) {
      const promptApis = JSON.parse(queueData);
      syncPromptRunApisAndStatus(promptApis);
    }

    // Setup the beforeunload event handler to store queue in cookies
    const handleBeforeUnload = () => {
      const { queue } = usePromptRunQueueStore.getState(); // Get the latest state dynamically
      if (queue?.length) {
        Cookies.set("promptRunQueue", JSON.stringify(queue), {
          expires: 5 / 1440, // Expire in 5 minutes
        });
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload); // Clean up event listener
    };
  }, [syncPromptRunApisAndStatus]);

  useEffect(() => {
    if (!queue?.length || activeApis >= MAX_ACTIVE_APIS) return;

    const canRunApis = MAX_ACTIVE_APIS - activeApis;
    const apisToRun = queue.slice(0, canRunApis);

    setPromptRunQueue({
      activeApis: activeApis + apisToRun.length,
      queue: queue.slice(apisToRun.length),
    });
    runPrompt(apisToRun);
  }, [activeApis, queue, setPromptRunQueue, runPrompt]);

  useEffect(() => {
    const isMultiPassExtractLoading = !!Object.keys(promptRunStatus).length;
    updateCustomTool({ isMultiPassExtractLoading });
  }, [promptRunStatus, updateCustomTool]);

  return null;
}

export { PromptRun };
