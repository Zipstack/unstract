import { useState } from "react";
import { Button, Card, Space, Typography, Alert, Divider, Spin } from "antd";
import {
  PlayCircleOutlined,
  BugOutlined,
  ClearOutlined,
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

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  const handleExecute = async () => {
    setExecuting(true);
    setResult(null);
    setError(null);

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
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup-projects/${project.id}/execute/`,
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
      setAlertDetails({
        type: "success",
        content: "Execution completed successfully",
      });
    } catch (error) {
      const errorMessage =
        error.response?.data?.error ||
        error.response?.data?.detail ||
        "Execution failed";
      setError(errorMessage);
      setAlertDetails({
        type: "error",
        content: errorMessage,
      });
    } finally {
      setExecuting(false);
    }
  };

  const handleClear = () => {
    setInputData("{}");
    setResult(null);
    setError(null);
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

      {error && (
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
