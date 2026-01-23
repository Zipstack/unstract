import { useState } from "react";
import {
  Button,
  Card,
  Space,
  Typography,
  Alert,
  Divider,
  Spin,
  Progress,
} from "antd";
import {
  PlayCircleOutlined,
  BugOutlined,
  ClearOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";
import CodeMirror from "@uiw/react-codemirror";
import { json } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./DebugTab.css";

const { Title, Text } = Typography;

export function DebugTab({ project }) {
  const [inputData, setInputData] = useState("{}");
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [errorDetails, setErrorDetails] = useState(null);

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  const handleExecute = async () => {
    setExecuting(true);
    setResult(null);
    setError(null);
    setErrorDetails(null);

    try {
      // Parse input JSON
      let parsedInput;
      try {
        parsedInput = JSON.parse(inputData);
      } catch (e) {
        setError("Invalid JSON input");
        setExecuting(false);
        return;
      }

      const response = await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/execute/`,
        {
          input_data: parsedInput,
          use_cache: false,
          timeout_seconds: 60,
        },
        {
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
        }
      );

      setResult(response.data);

      // Check for context window errors in failed enrichments (within successful response)
      const enrichments = response.data?._lookup_metadata?.enrichments || [];
      const contextWindowError = enrichments.find(
        (e) =>
          e.status === "failed" && e.error_type === "context_window_exceeded"
      );

      if (contextWindowError) {
        setErrorDetails({
          type: "context_window_exceeded",
          tokenCount: contextWindowError.token_count,
          contextLimit: contextWindowError.context_limit,
          model: contextWindowError.model,
        });
        setError(contextWindowError.error);
        setAlertDetails({
          type: "error",
          content: `Context window exceeded: ${contextWindowError.token_count?.toLocaleString()} tokens used, limit is ${contextWindowError.context_limit?.toLocaleString()}`,
        });
      } else if (response.data?._lookup_metadata?.lookups_failed > 0) {
        // Check for other failures
        const failedEnrichment = enrichments.find((e) => e.status === "failed");
        if (failedEnrichment) {
          setError(failedEnrichment.error);
          setAlertDetails({
            type: "error",
            content: failedEnrichment.error || "Look-Up execution failed",
          });
        }
      } else {
        setAlertDetails({
          type: "success",
          content: "Execution completed successfully",
        });
      }
    } catch (err) {
      const responseData = err.response?.data;
      const errorMessage =
        responseData?.error || responseData?.detail || "Execution failed";

      // Check for context window exceeded error in error response
      if (responseData?.error_type === "context_window_exceeded") {
        setErrorDetails({
          type: "context_window_exceeded",
          tokenCount: responseData.token_count,
          contextLimit: responseData.context_limit,
          model: responseData.model,
        });
        // Show specific popup for context window error
        setAlertDetails({
          type: "error",
          content: `Context window exceeded: ${responseData.token_count?.toLocaleString()} tokens required, limit is ${responseData.context_limit?.toLocaleString()}`,
        });
      } else {
        setAlertDetails({
          type: "error",
          content: errorMessage,
        });
      }

      setError(errorMessage);
    } finally {
      setExecuting(false);
    }
  };

  const handleClear = () => {
    setInputData("{}");
    setResult(null);
    setError(null);
    setErrorDetails(null);
  };

  const renderContextWindowError = () => {
    if (!errorDetails || errorDetails.type !== "context_window_exceeded") {
      return null;
    }

    const { tokenCount, contextLimit, model } = errorDetails;
    const usagePercent = Math.min(
      Math.round((tokenCount / contextLimit) * 100),
      100
    );
    const overflowAmount = tokenCount - contextLimit;
    const overflowPercent = Math.round((overflowAmount / contextLimit) * 100);

    return (
      <Alert
        message={
          <Space>
            <WarningOutlined />
            <span>Context Window Exceeded</span>
          </Space>
        }
        description={
          <div>
            <p style={{ marginBottom: 12 }}>
              The prompt requires{" "}
              <Text strong>{tokenCount.toLocaleString()}</Text> tokens, but the
              model <Text code>{model}</Text> has a limit of{" "}
              <Text strong>{contextLimit.toLocaleString()}</Text> tokens.
            </p>

            <div style={{ marginBottom: 16 }}>
              <Text
                type="secondary"
                style={{ marginBottom: 4, display: "block" }}
              >
                Token Usage ({usagePercent}% of limit, {overflowPercent}% over)
              </Text>
              <Progress
                percent={100}
                success={{
                  percent: Math.round((contextLimit / tokenCount) * 100),
                }}
                strokeColor="#f5222d"
                trailColor="#f5222d"
                showInfo={false}
              />
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginTop: 4,
                }}
              >
                <Text type="secondary">0</Text>
                <Text type="secondary">
                  Limit: {contextLimit.toLocaleString()}
                </Text>
                <Text type="danger">Used: {tokenCount.toLocaleString()}</Text>
              </div>
            </div>

            <Divider style={{ margin: "12px 0" }} />

            <Title level={5} style={{ marginTop: 0 }}>
              How to Fix
            </Title>
            <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
              <li>
                <Text strong>Enable RAG mode:</Text> Set chunk_size {"> 0"} in
                the profile to use vector retrieval instead of full context
              </li>
              <li>
                <Text strong>Reduce reference data:</Text> Remove unnecessary
                content from your data sources
              </li>
              <li>
                <Text strong>Use a larger model:</Text> Switch to a model with a
                larger context window (e.g., GPT-4-Turbo, Claude 3)
              </li>
              <li>
                <Text strong>Simplify your template:</Text> Reduce the prompt
                template size if possible
              </li>
            </ul>
          </div>
        }
        type="error"
        showIcon={false}
        style={{ marginBottom: 16 }}
      />
    );
  };

  const formatJSON = () => {
    try {
      const parsed = JSON.parse(inputData);
      setInputData(JSON.stringify(parsed, null, 2));
    } catch (e) {
      setAlertDetails({
        type: "warning",
        content: "Invalid JSON format",
      });
    }
  };

  return (
    <div className="debug-tab">
      <Title level={4}>Debug Console</Title>
      <Text type="secondary">
        Test your Look-Up configuration with sample data
      </Text>

      <Divider />

      <Alert
        message="Debug Mode"
        description="Executions in debug mode do not use caching and are not counted in statistics."
        type="info"
        showIcon
        icon={<BugOutlined />}
        style={{ marginBottom: 16 }}
      />

      <Card title="Input Data" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Text>
            Enter JSON data with variables that match your template
            placeholders:
          </Text>
          <CodeMirror
            value={inputData}
            height="200px"
            theme={oneDark}
            extensions={[json()]}
            onChange={(value) => setInputData(value)}
            editable={!executing}
          />
          <Space>
            <Button onClick={formatJSON} size="small">
              Format JSON
            </Button>
            <Text type="secondary">
              Example: {`{ "vendor_name": "Acme Corp", "product_id": "123" }`}
            </Text>
          </Space>
        </Space>
      </Card>

      <Space style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          onClick={handleExecute}
          loading={executing}
          disabled={!project.template}
        >
          Execute Look-Up
        </Button>
        <Button icon={<ClearOutlined />} onClick={handleClear}>
          Clear
        </Button>
      </Space>

      {!project.template && (
        <Alert
          message="No Template Configured"
          description="Please configure a template in the Template tab before debugging."
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {executing && (
        <Card style={{ marginBottom: 16 }}>
          <Space direction="vertical" align="center" style={{ width: "100%" }}>
            <Spin size="large" />
            <Text>Executing Look-Up...</Text>
          </Space>
        </Card>
      )}

      {error &&
        errorDetails?.type === "context_window_exceeded" &&
        renderContextWindowError()}

      {error && errorDetails?.type !== "context_window_exceeded" && (
        <Alert
          message="Execution Error"
          description={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {result && (
        <Card title="Execution Result">
          <Space direction="vertical" style={{ width: "100%" }}>
            {result.lookup_enrichment && (
              <>
                <Title level={5}>Enrichment Data</Title>
                <CodeMirror
                  value={JSON.stringify(result.lookup_enrichment, null, 2)}
                  height="200px"
                  theme={oneDark}
                  extensions={[json()]}
                  editable={false}
                />
              </>
            )}

            {result._lookup_metadata && (
              <>
                <Divider />
                <Title level={5}>Execution Metadata</Title>
                <Space direction="vertical">
                  <Text>
                    <strong>Lookups Executed:</strong>{" "}
                    {result._lookup_metadata.lookups_executed}
                  </Text>
                  <Text>
                    <strong>Successful:</strong>{" "}
                    {result._lookup_metadata.successful_lookups}
                  </Text>
                  <Text>
                    <strong>Failed:</strong>{" "}
                    {result._lookup_metadata.failed_lookups}
                  </Text>
                  <Text>
                    <strong>Execution Time:</strong>{" "}
                    {result._lookup_metadata.execution_time_ms}ms
                  </Text>
                  {result._lookup_metadata.conflicts_resolved > 0 && (
                    <Text type="warning">
                      <strong>Conflicts Resolved:</strong>{" "}
                      {result._lookup_metadata.conflicts_resolved}
                    </Text>
                  )}
                  {result._lookup_metadata.execution_id && (
                    <Text type="secondary">
                      <strong>Execution ID:</strong>{" "}
                      <Text code>{result._lookup_metadata.execution_id}</Text>
                    </Text>
                  )}
                </Space>
              </>
            )}
          </Space>
        </Card>
      )}
    </div>
  );
}

DebugTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
    template: PropTypes.object,
  }).isRequired,
};
