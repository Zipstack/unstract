import { useEffect, useState, useMemo } from "react";
import { Typography, Space, Alert, Tag } from "antd";
import {
  CheckCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import Editor from "@monaco-editor/react";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { promptType } from "../../../helpers/GetStaticData";
import "./CustomDataSettings.css";

// Regex to match {{custom_data.xyz}} variables in prompts
const CUSTOM_DATA_VARIABLE_REGEX = /\{\{custom_data\.([a-zA-Z0-9_.]+)\}\}/g;

// Helper function to extract all custom_data variables from text
const extractCustomDataVariables = (text) => {
  const variables = [];
  if (!text) return variables;

  const matches = text.matchAll(CUSTOM_DATA_VARIABLE_REGEX);
  for (const match of matches) {
    variables.push(match[1]);
  }
  return variables;
};

// Check if a nested variable path exists in the data
const checkVariableDefined = (data, variablePath) => {
  const parts = variablePath.split(".");
  let current = data;

  for (const part of parts) {
    if (current === null || current === undefined) {
      return false;
    }
    if (typeof current !== "object" || !(part in current)) {
      return false;
    }
    current = current[part];
  }

  return current !== undefined;
};

function CustomDataSettings() {
  const [jsonValue, setJsonValue] = useState("");
  const [jsonError, setJsonError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { details, isPublicSource, updateCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  // Initialize editor with current custom_data
  useEffect(() => {
    const customData = details?.custom_data;
    if (customData && Object.keys(customData).length > 0) {
      setJsonValue(JSON.stringify(customData, null, 2));
    } else {
      setJsonValue("{\n  \n}");
    }
    setHasChanges(false);
  }, [details?.custom_data]);

  // Extract variables from active prompts
  const extractedVariables = useMemo(() => {
    const prompts = details?.prompts || [];
    const variables = new Set();

    prompts.forEach((prompt) => {
      // Only scan active prompts (excluding notes)
      // Use !== false to include prompts where active is true or undefined
      if (
        prompt?.active !== false &&
        prompt?.prompt_type !== promptType.notes
      ) {
        const promptText = prompt?.prompt || "";
        const foundVariables = extractCustomDataVariables(promptText);
        foundVariables.forEach((v) => variables.add(v));
      }
    });

    return Array.from(variables);
  }, [details?.prompts]);

  // Parse current JSON and check which variables are defined
  const variableStatus = useMemo(() => {
    let parsedData = {};
    try {
      if (jsonValue && jsonValue.trim()) {
        parsedData = JSON.parse(jsonValue);
      }
    } catch {
      // If JSON is invalid, treat all as undefined
    }

    return extractedVariables.map((variable) => {
      const isDefined = checkVariableDefined(parsedData, variable);
      return { variable, isDefined };
    });
  }, [extractedVariables, jsonValue]);

  const handleEditorChange = (value) => {
    setJsonValue(value || "");
    setHasChanges(true);

    // Validate JSON
    try {
      if (value && value.trim()) {
        JSON.parse(value);
      }
      setJsonError(null);
    } catch (e) {
      setJsonError(e.message);
    }
  };

  const handleSave = () => {
    // Validate JSON before saving
    let customData = null;
    try {
      if (jsonValue && jsonValue.trim() && jsonValue.trim() !== "{}") {
        customData = JSON.parse(jsonValue);
        if (typeof customData !== "object" || Array.isArray(customData)) {
          setJsonError("Custom data must be a JSON object");
          return;
        }
      }
    } catch (e) {
      setJsonError(e.message);
      return;
    }

    const body = {
      custom_data: customData,
    };

    const requestOptions = {
      method: "PATCH",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/${details?.tool_id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        setHasChanges(false);
        // Update the store with the new details
        const updatedDetails = res?.data;
        if (updatedDetails) {
          updateCustomTool({ details: updatedDetails });
        }
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to save custom data"));
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  const undefinedCount = variableStatus.filter((v) => !v.isDefined).length;

  return (
    <div className="settings-body-pad-top">
      <SpaceWrapper>
        <div>
          <Typography.Text className="add-cus-tool-header">
            Custom Data
          </Typography.Text>
        </div>

        <div className="custom-data-description">
          <Typography.Text type="secondary">
            Define test data that can be referenced in prompts using{" "}
            <Typography.Text code>{"{{custom_data.key}}"}</Typography.Text>{" "}
            syntax. Supports nested access like{" "}
            <Typography.Text code>
              {"{{custom_data.user.name}}"}
            </Typography.Text>
            .
          </Typography.Text>
        </div>

        {jsonError && (
          <Alert
            message="Invalid JSON"
            description={jsonError}
            type="error"
            showIcon
            className="custom-data-error"
          />
        )}

        <div className="custom-data-editor-container">
          <Editor
            height="300px"
            language="json"
            value={jsonValue}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              fontSize: 14,
              lineNumbers: "on",
              tabSize: 2,
              automaticLayout: true,
              readOnly: isPublicSource,
              wordWrap: "on",
            }}
            theme="vs-dark"
          />
        </div>

        {extractedVariables.length > 0 && (
          <div className="custom-data-variables-section">
            <div className="custom-data-variables-header">
              <InfoCircleOutlined />
              <Typography.Text strong>
                Variables Referenced in Active Prompts
              </Typography.Text>
              {undefinedCount > 0 && (
                <Tag color="warning" className="custom-data-warning-tag">
                  {undefinedCount} undefined
                </Tag>
              )}
            </div>
            <div className="custom-data-variables-list">
              {variableStatus.map(({ variable, isDefined }) => (
                <div key={variable} className="custom-data-variable-item">
                  {isDefined ? (
                    <CheckCircleOutlined className="custom-data-icon-success" />
                  ) : (
                    <WarningOutlined className="custom-data-icon-warning" />
                  )}
                  <Typography.Text
                    code
                    className={
                      isDefined ? "" : "custom-data-variable-undefined"
                    }
                  >
                    custom_data.{variable}
                  </Typography.Text>
                  <Typography.Text
                    type={isDefined ? "success" : "warning"}
                    className="custom-data-variable-status"
                  >
                    {isDefined ? "(defined)" : "(not defined)"}
                  </Typography.Text>
                </div>
              ))}
            </div>
          </div>
        )}

        {extractedVariables.length === 0 && (
          <div className="custom-data-no-variables">
            <Typography.Text type="secondary">
              No custom_data variables found in active prompts. Add variables
              like{" "}
              <Typography.Text code>
                {"{{custom_data.your_key}}"}
              </Typography.Text>{" "}
              to your prompts to use this feature.
            </Typography.Text>
          </div>
        )}

        <div className="display-flex-right">
          <Space>
            <CustomButton
              type="primary"
              onClick={handleSave}
              loading={isLoading}
              disabled={isPublicSource || !!jsonError || !hasChanges}
            >
              Save
            </CustomButton>
          </Space>
        </div>
      </SpaceWrapper>
    </div>
  );
}

export { CustomDataSettings };
