import { EditOutlined, MinusOutlined } from "@ant-design/icons";
import { Button, Input, Typography } from "antd";
import { useState } from "react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useWorkflowStore } from "../../../store/workflow-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import "./Prompt.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function Prompt() {
  const [isPromptOpen, setIsPromptOpen] = useState(false);
  const axiosPrivate = useAxiosPrivate();
  const { prompt, isLoading, details, updateWorkflow } = useWorkflowStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const handlePromptChange = (e) => {
    const promptText = e.target.value;
    updateWorkflow({ prompt: promptText });
  };

  const handleGenerateWorkflow = () => {
    const workflowId = details?.id;

    if (!workflowId) {
      setAlertDetails({
        type: "error",
        content: "Invalid workflow Id",
      });
      return;
    }
    const body = {
      prompt_name: "Prompt #1",
      prompt_text: prompt,
      workflow_name: details?.workflow_name,
    };

    const requestOptions = {
      method: "PUT",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/workflow/${workflowId}/`,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: body,
    };

    const workflowState = {
      isLoading: true,
      loadingType: "GENERATE",
    };

    updateWorkflow(workflowState);
    setIsPromptOpen(false);
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        workflowState["details"] = data || {};
      })
      .catch((err) => {
        setIsPromptOpen(true);
        setAlertDetails(
          handleException(err, "Failed to generate the workflow"),
        );
      })
      .finally(() => {
        workflowState["isLoading"] = false;
        workflowState["loadingType"] = "";
        updateWorkflow(workflowState);
      });
  };

  return (
    <div className="wf-prompt-layout">
      {isPromptOpen ? (
        <div>
          <div className="wf-prompt-textarea-header">
            <div>
              <Typography.Text strong>
                Workflow Generation Prompt
              </Typography.Text>
            </div>
            <div className="edit-btn">
              <Button
                size="small"
                type="text"
                onClick={() => setIsPromptOpen(false)}
              >
                <MinusOutlined />
              </Button>
            </div>
          </div>
          <div className="wf-prompt-textarea">
            <Input.TextArea
              rows={4}
              value={prompt}
              onChange={handlePromptChange}
            />
          </div>
          <div className="wf-prompt-btn display-flex-right">
            <CustomButton
              type="primary"
              onClick={handleGenerateWorkflow}
              disabled={isLoading}
            >
              Generate Workflow
            </CustomButton>
          </div>
        </div>
      ) : (
        <div className="wf-prompt-textarea-header">
          <div style={{ overflow: "hidden" }}>
            <Typography.Text ellipsis strong>
              {prompt || "Workflow Generation Prompt"}
            </Typography.Text>
          </div>
          <div className="edit-btn">
            <Button
              size="small"
              type="text"
              onClick={() => setIsPromptOpen(true)}
            >
              <EditOutlined />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export { Prompt };
