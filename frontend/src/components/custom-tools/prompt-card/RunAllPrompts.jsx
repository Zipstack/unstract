import { CirclePlay, FastForward } from "lucide-react";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { PROMPT_RUN_TYPES } from "../../../helpers/GetStaticData";
import usePromptRun from "../../../hooks/usePromptRun";
import { useCustomToolStore } from "../../../store/custom-tool-store";

function RunAllPrompts() {
  const { selectedDoc, isMultiPassExtractLoading, isPublicSource } =
    useCustomToolStore();
  const { handlePromptRunRequest } = usePromptRun();

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
          disabled={isMultiPassExtractLoading || isPublicSource}
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
          disabled={isMultiPassExtractLoading || isPublicSource}
        />
      </Tooltip>
    </Space>
  );
}

export { RunAllPrompts };
