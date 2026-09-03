import { CirclePlay, FastForward, Square } from "lucide-react";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { PROMPT_RUN_TYPES } from "../../../helpers/GetStaticData";
import usePromptRun from "../../../hooks/usePromptRun";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";

function RunAllPrompts() {
  const {
    selectedDoc,
    isMultiPassExtractLoading,
    isSinglePassExtractLoading,
    isPublicSource,
  } = useCustomToolStore();
  const { handlePromptRunRequest, stopAllRuns } = usePromptRun();
  const activeRuns = usePromptRunStatusStore((state) => state.activeRuns);

  const isRunning = isMultiPassExtractLoading || isSinglePassExtractLoading;
  // Only runs this hook started are cancellable — a run dispatched elsewhere
  // (the cloud single-pass button, until it registers its run_id) has no id to
  // name, so we keep today's disabled-while-running buttons rather than
  // offering a Stop that would do nothing (UN-1031).
  const stoppableRuns = Object.keys(activeRuns || {});
  const canStop = isRunning && stoppableRuns.length > 0;
  // Every in-flight run has already been told to stop; the button stays out of
  // the way until the executors reach their next checkpoints.
  const isStopping =
    canStop && Object.values(activeRuns).every((run) => run?.stopping);

  if (canStop) {
    return (
      <Tooltip title={isStopping ? "Stopping…" : "Stop all running prompts"}>
        <Button
          data-testid="ps-stop-all-prompts-btn"
          icon={<Square className="prompt-card-actions-head" />}
          onClick={stopAllRuns}
          disabled={isStopping || isPublicSource}
        />
      </Tooltip>
    );
  }

  return (
    <Space>
      <Tooltip title="Run all prompts for all LLMs and current document">
        <Button
          data-testid="ps-run-all-prompts-one-doc-btn"
          icon={<CirclePlay className="prompt-card-actions-head" />}
          onClick={() =>
            handlePromptRunRequest(
              PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ONE_DOC,
              null,
              null,
              selectedDoc?.document_id,
            )
          }
          disabled={isRunning || isPublicSource}
        />
      </Tooltip>
      <Tooltip title="Run all prompts for all LLMs and documents">
        <Button
          data-testid="ps-run-all-prompts-all-docs-btn"
          // All-documents runs use FastForward; the single-document button
          // beside it keeps CirclePlay, so the two are told apart at a glance.
          icon={<FastForward className="prompt-card-actions-head" />}
          onClick={() =>
            handlePromptRunRequest(
              PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ALL_DOCS,
              null,
              null,
              null,
            )
          }
          disabled={isRunning || isPublicSource}
        />
      </Tooltip>
    </Space>
  );
}

export { RunAllPrompts };
