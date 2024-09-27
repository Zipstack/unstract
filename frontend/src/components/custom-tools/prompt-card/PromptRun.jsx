import { useEffect } from "react";
import Cookies from "js-cookie";

import { usePromptRunQueueStore } from "../../../store/prompt-run-queue-store";
import usePromptRun from "../../../hooks/usePromptRun";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";
import { PROMPT_RUN_API_STATUSES } from "../../../helpers/GetStaticData";

const MAX_ACTIVE_APIS = 5;

function PromptRun() {
  const promptRunQueueStore = usePromptRunQueueStore();
  const { setPromptRunQueue } = promptRunQueueStore;
  const { runPrompt, syncPromptRunApisAndStatus } = usePromptRun();
  const { promptRunStatus } = usePromptRunStatusStore();
  const { updateCustomTool } = useCustomToolStore();

  useEffect(() => {
    const queueData = Cookies.get("promptRunQueue");
    if (queueData && JSON.parse(queueData)) {
      const promptApis = JSON.parse(queueData);
      syncPromptRunApisAndStatus(promptApis);
    }

    window.onbeforeunload = () => {
      const { queue } = promptRunQueueStore;
      Cookies.set("promptRunQueue", JSON.stringify(queue), {
        expires: 5 / 1440,
      });
    };
  }, []);

  useEffect(() => {
    const { activeApis, queue } = promptRunQueueStore;

    if (!queue?.length || activeApis >= MAX_ACTIVE_APIS) return;

    const canRunApis = MAX_ACTIVE_APIS - activeApis;
    const apisToRun = [...queue].splice(0, canRunApis);

    setPromptRunQueue({
      activeApis: activeApis + apisToRun?.length,
      queue: [...queue].slice(apisToRun?.length),
    });
    runPrompt(apisToRun);
  }, [promptRunQueueStore]);

  useEffect(() => {
    const isMultiPassExtractLoading = !!Object.keys(promptRunStatus)?.filter(
      (key) => promptRunStatus[key] === PROMPT_RUN_API_STATUSES.RUNNING
    )?.length;
    updateCustomTool({ isMultiPassExtractLoading });
  }, [promptRunStatus]);
}

export { PromptRun };
