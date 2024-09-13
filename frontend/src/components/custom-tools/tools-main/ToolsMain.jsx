import { Tabs, Tooltip } from "antd";
import { useEffect, useState } from "react";
import { TableOutlined, UnorderedListOutlined } from "@ant-design/icons";

import { getSequenceNumber, promptType } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CombinedOutput } from "../combined-output/CombinedOutput";
import { DocumentParser } from "../document-parser/DocumentParser";
import { Footer } from "../footer/Footer";
import "./ToolsMain.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { ToolsMainActionBtns } from "./ToolsMainActionBtns";
import usePromptOutput from "../../../hooks/usePromptOutput";
import { usePromptOutputStore } from "../../../store/prompt-output-store";

function ToolsMain() {
  const [activeKey, setActiveKey] = useState("1");
  const [prompts, setPrompts] = useState([]);
  const [scrollToBottom, setScrollToBottom] = useState(false);
  const { sessionDetails } = useSessionStore();
  const {
    details,
    defaultLlmProfile,
    selectedDoc,
    updateCustomTool,
    disableLlmOrDocChange,
    isSimplePromptStudio,
    singlePassExtractMode,
  } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { setPromptOutput } = usePromptOutputStore();
  const { promptOutputApi, generatePromptOutputKey } = usePromptOutput();

  const items = [
    {
      key: "1",
      label: isSimplePromptStudio ? (
        <Tooltip title="Fields">
          <UnorderedListOutlined />
        </Tooltip>
      ) : (
        "Document Parser"
      ),
    },
    {
      key: "2",
      label: isSimplePromptStudio ? (
        <Tooltip title="Combined Output">
          <TableOutlined />
        </Tooltip>
      ) : (
        "Combined Output"
      ),
      disabled: prompts?.length === 0 || disableLlmOrDocChange?.length > 0,
    },
  ];

  useEffect(() => {
    promptOutputApi(
      details?.tool_id,
      selectedDoc?.document_id,
      null,
      null,
      singlePassExtractMode
    )
      .then((res) => {
        const data = res?.data || [];
        console.log(data);

        const outputs = {};
        data.forEach((outputResult) => {
          const promptId = outputResult?.prompt_id;
          const docId = outputResult?.document_manager;
          const llmProfile = outputResult?.profile_manager;
          const isSinglePass = outputResult?.is_single_pass_extract;

          if (!promptId || !docId || !llmProfile) {
            return;
          }

          const key = generatePromptOutputKey(
            promptId,
            docId,
            llmProfile,
            isSinglePass
          );

          outputs[key] = {
            runId: outputResult?.run_id,
            promptOutputId: outputResult?.prompt_output_id,
            profileManager: outputResult?.profile_manager,
            context: outputResult?.context,
            challengeData: outputResult?.challenge_data,
            output: outputResult?.output,
          };
        });

        setPromptOutput(outputs);
      })
      .catch((err) => {
        console.log(err);
      });
  }, [selectedDoc, singlePassExtractMode]);

  const getPromptKey = (len) => {
    const promptKey = `${details?.tool_name}_${len}`;

    const index = [...prompts].findIndex(
      (item) => item?.prompt_key === promptKey
    );

    if (index === -1) {
      return promptKey;
    }

    return getPromptKey(len + 1);
  };

  const defaultPromptInstance = {
    prompt_key: getPromptKey(prompts?.length + 1),
    prompt: "",
    tool_id: details?.tool_id,
    prompt_type: promptType.prompt,
    profile_manager: defaultLlmProfile,
    sequence_number: getSequenceNumber(prompts),
  };

  const defaultNoteInstance = {
    prompt_key: getPromptKey(prompts?.length + 1),
    prompt: "",
    tool_id: details?.tool_id,
    prompt_type: promptType.notes,
    sequence_number: getSequenceNumber(prompts),
  };

  useEffect(() => {
    setPrompts(details?.prompts || []);
  }, [details]);

  const onChange = (key) => {
    setActiveKey(key);
  };

  const addPromptInstance = (type) => {
    try {
      setPostHogCustomEvent("ps_prompt_added", {
        info: `Clicked on + ${type} button`,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }

    let body = {};
    if (type === promptType.prompt) {
      body = { ...defaultPromptInstance };
    } else {
      body = { ...defaultNoteInstance };
    }
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-studio-prompt/${details?.tool_id}/`,

      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const modifiedDetails = { ...details };
        const modifiedPrompts = modifiedDetails?.prompts || [];
        modifiedPrompts.push(data);
        modifiedDetails["prompts"] = modifiedPrompts;
        updateCustomTool({ details: modifiedDetails });
        setScrollToBottom(true);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to add"));
      });
  };

  return (
    <div className="tools-main-layout">
      <div className="doc-manager-header">
        <div className="tools-main-tabs">
          <Tabs
            activeKey={activeKey}
            items={items}
            onChange={onChange}
            moreIcon={<></>}
          />
        </div>
        <div className="display-flex-align-center">
          <ToolsMainActionBtns />
        </div>
      </div>
      <div className="tools-main-body">
        {activeKey === "1" && (
          <DocumentParser
            addPromptInstance={addPromptInstance}
            scrollToBottom={scrollToBottom}
            setScrollToBottom={setScrollToBottom}
          />
        )}
        {activeKey === "2" && (
          <CombinedOutput docId={selectedDoc?.document_id} />
        )}
      </div>
      {!isSimplePromptStudio && (
        <div className="tools-main-footer">
          <Footer activeKey={activeKey} addPromptInstance={addPromptInstance} />
        </div>
      )}
    </div>
  );
}

export { ToolsMain };
