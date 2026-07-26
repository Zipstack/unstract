import { CirclePlay } from "lucide-react";
import { Button } from "@/components/ui/antd-button";
import { Space } from "@/components/ui/antd-layout";
import { Tooltip } from "@/components/ui/antd-overlays";
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
          icon={<CirclePlay className="prompt-card-actions-head" />}
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
