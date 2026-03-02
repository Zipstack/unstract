import { useState, useEffect, useCallback } from "react";
import {
  Button,
  Card,
  Space,
  Typography,
  Alert,
  Divider,
  Spin,
  Progress,
  Tooltip,
} from "antd";
import {
  PlayCircleOutlined,
  BugOutlined,
  ClearOutlined,
  WarningOutlined,
  SyncOutlined,
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

// Default sample JSON when no linked projects are found
const DEFAULT_SAMPLE_JSON = {
  vendor_name: "Acme Corporation",
  product_id: "SKU-12345",
  invoice_number: "INV-2024-001",
  amount: 1250.0,
  currency: "USD",
};

// Sample values for common prompt key patterns
const SAMPLE_VALUES = {
  vendor_name: "Acme Corporation",
  vendor: "Acme Corp",
  product_name: "Widget Pro X",
  product_id: "SKU-12345",
  product: "Widget",
  invoice_number: "INV-2024-001",
  invoice_id: "INV-001",
  amount: 1250.0,
  price: 99.99,
  total: 1500.0,
  currency: "USD",
  date: "2024-01-15",
  customer_name: "John Doe",
  customer: "John Doe",
  email: "customer@example.com",
  phone: "+1-555-123-4567",
  address: "123 Main St, City, State 12345",
  description: "Sample product description",
  quantity: 10,
  category: "Electronics",
  status: "pending",
  order_id: "ORD-2024-001",
  sku: "SKU-12345",
  brand: "BrandName",
  model: "Model-X",
  serial_number: "SN-123456789",
};

/**
 * Generates a sample value for a prompt key.
 * @param {string} promptKey - The prompt key to generate a sample value for.
 * @return {string|number} A sample value appropriate for the prompt key.
 */
const getSampleValue = (promptKey) => {
  const lowerKey = promptKey.toLowerCase().replace(/[-_\s]/g, "_");

  // Check for exact match
  if (SAMPLE_VALUES[lowerKey]) {
    return SAMPLE_VALUES[lowerKey];
  }

  // Check for partial matches
  for (const [key, value] of Object.entries(SAMPLE_VALUES)) {
    if (lowerKey.includes(key) || key.includes(lowerKey)) {
      return value;
    }
  }

  // Generate reasonable defaults based on key patterns
  if (lowerKey.includes("id") || lowerKey.includes("number")) {
    return "12345";
  }
  if (lowerKey.includes("date") || lowerKey.includes("time")) {
    return "2024-01-15";
  }
  if (
    lowerKey.includes("amount") ||
    lowerKey.includes("price") ||
    lowerKey.includes("total")
  ) {
    return 100.0;
  }
  if (lowerKey.includes("email")) {
    return "example@email.com";
  }
  if (lowerKey.includes("name")) {
    return "Sample Name";
  }

  // Default placeholder
  return `sample_${promptKey}`;
};

/**
 * Builds sample JSON from an array of prompt keys.
 * @param {string[]} promptKeys - Array of prompt keys from the linked project.
 * @return {Object} A sample JSON object with prompt keys as fields.
 */
const buildSampleJsonFromPromptKeys = (promptKeys) => {
  if (!promptKeys || promptKeys.length === 0) {
    return DEFAULT_SAMPLE_JSON;
  }

  const sample = {};
  promptKeys.forEach((key) => {
    sample[key] = getSampleValue(key);
  });
  return sample;
};

/**
 * Merges original input data with lookup enrichment results.
 * Enriched fields override original fields, and new enriched fields are added.
 * @param {Object} originalInput - The original input JSON.
 * @param {Object} enrichment - The lookup enrichment result.
 * @return {Object} Merged result with original fields + enriched/replaced values.
 */
const mergeInputWithEnrichment = (originalInput, enrichment) => {
  if (!enrichment) {
    return originalInput;
  }
  // Merge: original input fields + enrichment fields (enrichment overrides)
  return {
    ...originalInput,
    ...enrichment,
  };
};

export function DebugTab({ project }) {
  const [inputData, setInputData] = useState(
    JSON.stringify(DEFAULT_SAMPLE_JSON, null, 2)
  );
  const [loadingPromptKeys, setLoadingPromptKeys] = useState(false);
  const [linkedProjectInfo, setLinkedProjectInfo] = useState(null);
  const [executing, setExecuting] = useState(false);
  const [result, setResult] = useState(null);
  const [parsedInput, setParsedInput] = useState(null); // Store parsed input for merging
  const [error, setError] = useState(null);
  const [errorDetails, setErrorDetails] = useState(null);

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  /**
   * Fetches linked Prompt Studio projects and their prompt keys,
   * then builds a sample JSON for the debug input.
   */
  const fetchLinkedProjectPromptKeys = useCallback(async () => {
    if (!sessionDetails?.orgId || !project?.id) return;

    setLoadingPromptKeys(true);
    try {
      // Step 1: Fetch linked Prompt Studio projects
      const linksResponse = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails.orgId}/lookup/lookup-links/`,
        { params: { lookup_project_id: project.id } }
      );

      const links = linksResponse.data.results || [];
      if (links.length === 0) {
        // No linked projects, use default sample
        setInputData(JSON.stringify(DEFAULT_SAMPLE_JSON, null, 2));
        setLinkedProjectInfo(null);
        return;
      }

      // Step 2: Fetch the first linked Prompt Studio project details
      const firstLink = links[0];
      const psProjectId = firstLink.prompt_studio_project_id;

      const psResponse = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails.orgId}/prompt-studio/${psProjectId}/`
      );

      const psProject = psResponse.data;
      const prompts = psProject.prompts || [];

      // Step 3: Extract prompt keys (excluding notes)
      const promptKeys = prompts
        .filter((p) => p.prompt_type === "PROMPT" || !p.prompt_type)
        .map((p) => p.prompt_key)
        .filter((key) => key && key !== "Enter key");

      // Step 4: Build sample JSON
      const sampleJson = buildSampleJsonFromPromptKeys(promptKeys);
      setInputData(JSON.stringify(sampleJson, null, 2));

      setLinkedProjectInfo({
        projectName: psProject.tool_name || "Linked Project",
        promptCount: promptKeys.length,
        promptKeys: promptKeys,
      });
    } catch (error) {
      console.error("Failed to fetch linked project prompt keys:", error);
      // On error, fall back to default sample
      setInputData(JSON.stringify(DEFAULT_SAMPLE_JSON, null, 2));
      setLinkedProjectInfo(null);
    } finally {
      setLoadingPromptKeys(false);
    }
  }, [axiosPrivate, sessionDetails?.orgId, project?.id]);

  // Fetch linked project prompt keys on mount
  useEffect(() => {
    fetchLinkedProjectPromptKeys();
  }, [fetchLinkedProjectPromptKeys]);

  const handleExecute = async () => {
    setExecuting(true);
    setResult(null);
    setParsedInput(null);
    setError(null);
    setErrorDetails(null);

    try {
      // Parse input JSON
      let inputJson;
      try {
        inputJson = JSON.parse(inputData);
      } catch (e) {
        setError("Invalid JSON input");
        setExecuting(false);
        return;
      }

      // Store parsed input for later merging with results
      setParsedInput(inputJson);

      const response = await axiosPrivate.post(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-projects/${project.id}/execute/`,
        {
          input_data: inputJson,
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
    // Reset to sample JSON based on linked project or default
    if (linkedProjectInfo?.promptKeys?.length > 0) {
      const sampleJson = buildSampleJsonFromPromptKeys(
        linkedProjectInfo.promptKeys
      );
      setInputData(JSON.stringify(sampleJson, null, 2));
    } else {
      setInputData(JSON.stringify(DEFAULT_SAMPLE_JSON, null, 2));
    }
    setResult(null);
    setError(null);
    setErrorDetails(null);
  };

  const handleRefreshSample = () => {
    fetchLinkedProjectPromptKeys();
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

      <Card
        title={
          <Space>
            <span>Input Data</span>
            {loadingPromptKeys && <Spin size="small" />}
          </Space>
        }
        extra={
          <Tooltip title="Refresh sample data from linked Prompt Studio project">
            <Button
              icon={<SyncOutlined spin={loadingPromptKeys} />}
              size="small"
              onClick={handleRefreshSample}
              disabled={loadingPromptKeys}
            >
              Refresh Sample
            </Button>
          </Tooltip>
        }
        style={{ marginBottom: 16 }}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          {linkedProjectInfo ? (
            <Alert
              message={
                <span>
                  Sample data generated from{" "}
                  <Text strong>{linkedProjectInfo.projectName}</Text> (
                  {linkedProjectInfo.promptCount} prompt field
                  {linkedProjectInfo.promptCount !== 1 ? "s" : ""})
                </span>
              }
              type="success"
              showIcon
              style={{ marginBottom: 8 }}
            />
          ) : (
            <Text type="secondary">
              Enter JSON data with field values to test your Look-Up. Link a
              Prompt Studio project to auto-populate sample fields.
            </Text>
          )}
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
            {linkedProjectInfo && (
              <Text type="secondary">
                Fields: {linkedProjectInfo.promptKeys.join(", ")}
              </Text>
            )}
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
            {result.lookup_enrichment && parsedInput && (
              <>
                <Title level={5}>Enriched Output</Title>
                <Text type="secondary" style={{ marginBottom: 8 }}>
                  Original input fields combined with lookup enrichment values
                </Text>
                <CodeMirror
                  value={JSON.stringify(
                    mergeInputWithEnrichment(
                      parsedInput,
                      result.lookup_enrichment
                    ),
                    null,
                    2
                  )}
                  height="200px"
                  theme={oneDark}
                  extensions={[json()]}
                  editable={false}
                />
                <Divider />
                <Title level={5}>Lookup Enrichment Only</Title>
                <Text type="secondary" style={{ marginBottom: 8 }}>
                  Fields that were enriched or added by the lookup
                </Text>
                <CodeMirror
                  value={JSON.stringify(result.lookup_enrichment, null, 2)}
                  height="150px"
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
