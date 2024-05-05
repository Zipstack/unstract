import { BarChartOutlined } from "@ant-design/icons";
import { Button, Space, Tabs, Tooltip } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { promptType } from "../../../helpers/GetStaticData";
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

let RunSinglePassBtn;
try {
  RunSinglePassBtn =
    require("../../../plugins/run-single-pass-btn/RunSinglePassBtn").RunSinglePassBtn;
} catch {
  // The variable is remain undefined if the component is not available
}

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
    singlePassExtractMode,
    isSinglePassExtractLoading,
  } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const navigate = useNavigate();
  const { setPostHogCustomEvent } = usePostHogEvents();

  const items = [
    {
      key: "1",
      label: "Document Parser",
    },
    {
      key: "2",
      label: "Combined Output",
      disabled: prompts?.length === 0 || disableLlmOrDocChange?.length > 0,
    },
  ];

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

  const getSequenceNumber = () => {
    let maxSequenceNumber = 0;
    prompts.forEach((item) => {
      if (item?.sequence_number > maxSequenceNumber) {
        maxSequenceNumber = item?.sequence_number;
      }
    });

    return maxSequenceNumber + 1;
  };

  const defaultPromptInstance = {
    prompt_key: getPromptKey(prompts?.length + 1),
    prompt: "",
    tool_id: details?.tool_id,
    prompt_type: promptType.prompt,
    is_assert: false,
    profile_manager: defaultLlmProfile,
    sequence_number: getSequenceNumber(),
  };

  const defaultNoteInstance = {
    prompt_key: getPromptKey(prompts?.length + 1),
    prompt: "",
    tool_id: details?.tool_id,
    prompt_type: promptType.notes,
    sequence_number: getSequenceNumber(),
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

  const handleOutputAnalyzerBtnClick = () => {
    navigate("outputAnalyzer");

    try {
      setPostHogCustomEvent("ps_output_analyser_seen", {
        info: "Clicked on 'Output Analyzer' button",
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  return (
    <div className="tools-main-layout">
      <div className="doc-manager-header">
        <div className="tools-main-tabs">
          <Tabs activeKey={activeKey} items={items} onChange={onChange} />
        </div>
        <div className="display-flex-align-center">
          <Space>
            <Tooltip title="Output Analyzer">
              <Button
                icon={<BarChartOutlined />}
                onClick={handleOutputAnalyzerBtnClick}
                disabled={
                  disableLlmOrDocChange?.length > 0 ||
                  isSinglePassExtractLoading
                }
              />
            </Tooltip>
            {singlePassExtractMode && RunSinglePassBtn && <RunSinglePassBtn />}
          </Space>
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
      <div className="tools-main-footer">
        <Footer activeKey={activeKey} addPromptInstance={addPromptInstance} />
      </div>
    </div>
  );
}

export { ToolsMain };
