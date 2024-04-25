import {
  BarChartOutlined,
  FileAddOutlined,
  TagsOutlined,
} from "@ant-design/icons";
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
import { ManageTags } from "../manage-tags/ManageTags";
import "./ToolsMain.css";

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
  const [openTags, setOpenTags] = useState(false);
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
          <Tabs activeKey={activeKey} items={items} onChange={onChange} />
        </div>
        <div className="display-flex-align-center">
          <Space>
            <div>
              <Tooltip title="Manage Tags">
                <Button
                  icon={<TagsOutlined />}
                  onClick={() => setOpenTags(true)}
                />
              </Tooltip>
            </div>
            <Tooltip title="Tag Check-In">
              <Button
                icon={<FileAddOutlined />}
                onClick={() => navigate("outputAnalyzer")}
              />
            </Tooltip>
            <Tooltip title="Output Analyzer">
              <Button
                icon={<BarChartOutlined />}
                onClick={() => navigate("outputAnalyzer")}
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
      <ManageTags open={openTags} setOpen={setOpenTags} />
    </div>
  );
}

export { ToolsMain };
