import { PlayCircleFilled, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip } from "antd";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePromptRun from "../../../hooks/usePromptRun";
import { PROMPT_RUN_TYPES } from "../../../helpers/GetStaticData";

function RunAllPrompts() {
  const { selectedDoc, isMultiPassExtractLoading, isPublicSource } =
    useCustomToolStore();
  const { handlePromptRunRequest } = usePromptRun();

  return (
    <Space>
      <Tooltip title="Run all prompts for all LLMs and current document">
        <Button
          icon={<PlayCircleOutlined className="prompt-card-actions-head" />}
          onClick={() =>
            handlePromptRunRequest(
              PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ALL_LLMS_ONE_DOC,
              null,
              null,
              selectedDoc?.document_id
            )
          }
          disabled={isMultiPassExtractLoading || isPublicSource}
        />
      </Tooltip>
      <Tooltip title="Run all prompts for all LLMs and documents">
        <Button
          icon={<PlayCircleFilled className="prompt-card-actions-head" />}
          onClick={() =>
            handlePromptRunRequest(
              PROMPT_RUN_TYPES.RUN_ALL_PROMPTS_ONE_LLM_ALL_DOCS,
              null,
              null,
              null
            )
          }
          disabled={isMultiPassExtractLoading || isPublicSource}
        />
      </Tooltip>
    </Space>
  );
}

export { RunAllPrompts };
