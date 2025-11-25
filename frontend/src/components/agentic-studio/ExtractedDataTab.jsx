import { useState, useEffect } from "react";
import {
  Button,
  Space,
  Alert,
  Spin,
  Typography,
  Card,
  Select,
  Empty,
  Tabs,
  Table,
  Tag,
  Switch,
  Row,
  Col,
  Statistic,
} from "antd";
import {
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined,
  FileTextOutlined,
  CodeOutlined,
} from "@ant-design/icons";
import MonacoEditor from "@monaco-editor/react";
import PropTypes from "prop-types";

import {
  extractionApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";

const { Title, Text } = Typography;

// Recursive function to flatten nested objects for comparison
const flattenObject = (obj, prefix = "") => {
  const flattened = {};

  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const newKey = prefix ? `${prefix}.${key}` : key;

    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(flattened, flattenObject(value, newKey));
    } else {
      flattened[newKey] = value;
    }
  });

  return flattened;
};

// Compare two values and determine match status
const compareValues = (extracted, verified) => {
  if (extracted === verified) return "match";
  if (extracted === null || verified === null) return "partial";

  // String comparison (case-insensitive)
  if (typeof extracted === "string" && typeof verified === "string") {
    if (extracted.toLowerCase().trim() === verified.toLowerCase().trim()) {
      return "match";
    }
  }

  // Number comparison with tolerance
  if (typeof extracted === "number" && typeof verified === "number") {
    if (Math.abs(extracted - verified) < 0.01) {
      return "match";
    }
  }

  return "mismatch";
};

function ExtractedDataTab({
  projectId,
  documents,
  selectedDocId,
  onSelectDocument,
}) {
  const [extractedData, setExtractedData] = useState(null);
  const [verifiedData, setVerifiedData] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState("data"); // 'data' or 'json'
  const [hideEmpty, setHideEmpty] = useState(false);
  const [showMismatchOnly, setShowMismatchOnly] = useState(false);
  const [comparisonData, setComparisonData] = useState([]);

  useEffect(() => {
    if (projectId && selectedDocId) {
      loadData();
    }
    // eslint-disable-next-line
  }, [projectId, selectedDocId]);

  useEffect(() => {
    if (extractedData && verifiedData) {
      performComparison();
    }
    // eslint-disable-next-line
  }, [extractedData, verifiedData, hideEmpty, showMismatchOnly]);

  const loadData = async () => {
    try {
      setLoading(true);

      // Load extracted data
      const extractedResp = await extractionApi.getExtractedData(
        projectId,
        selectedDocId
      );
      setExtractedData(extractedResp);

      // Load verified data
      try {
        const verifiedResp = await extractionApi.getVerifiedData(
          projectId,
          selectedDocId
        );
        setVerifiedData(verifiedResp);
      } catch (error) {
        if (error.response?.status !== 404) {
          console.error("Failed to load verified data:", error);
        }
        setVerifiedData(null);
      }

      // Load comparison if available
      try {
        const comparisonResp = await extractionApi.getDocumentComparison(
          projectId,
          selectedDocId
        );
        setComparison(comparisonResp);
      } catch (error) {
        if (error.response?.status !== 404) {
          console.error("Failed to load comparison:", error);
        }
        setComparison(null);
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        showApiError(error, "Failed to load extracted data");
      }
      setExtractedData(null);
    } finally {
      setLoading(false);
    }
  };

  const performComparison = () => {
    if (!extractedData || !verifiedData) {
      setComparisonData([]);
      return;
    }

    const extractedFlat = flattenObject(extractedData.data || {});
    const verifiedFlat = flattenObject(verifiedData.data || {});

    // Get all unique field paths
    const allFields = new Set([
      ...Object.keys(extractedFlat),
      ...Object.keys(verifiedFlat),
    ]);

    const comparisonResults = [];

    allFields.forEach((fieldPath) => {
      const extractedValue = extractedFlat[fieldPath];
      const verifiedValue = verifiedFlat[fieldPath];

      // Skip if hideEmpty is true and both values are empty
      if (
        hideEmpty &&
        (extractedValue === null || extractedValue === "") &&
        (verifiedValue === null || verifiedValue === "")
      ) {
        return;
      }

      const status = compareValues(extractedValue, verifiedValue);

      // Skip if showMismatchOnly is true and status is match
      if (showMismatchOnly && status === "match") {
        return;
      }

      comparisonResults.push({
        fieldPath,
        extractedValue,
        verifiedValue,
        status,
      });
    });

    setComparisonData(comparisonResults);
  };

  const selectedDocument = documents.find((d) => d.id === selectedDocId);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  // Calculate statistics
  const totalFields = comparisonData.length;
  const matchedFields = comparisonData.filter(
    (f) => f.status === "match"
  ).length;
  const mismatchedFields = comparisonData.filter(
    (f) => f.status === "mismatch"
  ).length;
  const accuracy =
    totalFields > 0 ? ((matchedFields / totalFields) * 100).toFixed(1) : 0;

  // Table columns for comparison view
  const columns = [
    {
      title: "Field Path",
      dataIndex: "fieldPath",
      key: "fieldPath",
      width: 250,
      fixed: "left",
      render: (text) => (
        <Text code style={{ fontSize: "12px" }}>
          {text}
        </Text>
      ),
    },
    {
      title: "Extracted Value",
      dataIndex: "extractedValue",
      key: "extractedValue",
      width: 300,
      render: (value) => {
        if (value === null || value === undefined) {
          return <Text type="secondary">null</Text>;
        }
        if (typeof value === "object") {
          return (
            <Text code style={{ wordBreak: "break-word", fontSize: "11px" }}>
              {JSON.stringify(value, null, 2)}
            </Text>
          );
        }
        return <Text style={{ wordBreak: "break-word" }}>{String(value)}</Text>;
      },
    },
    {
      title: "Verified Value",
      dataIndex: "verifiedValue",
      key: "verifiedValue",
      width: 300,
      render: (value) => {
        if (value === null || value === undefined) {
          return <Text type="secondary">null</Text>;
        }
        if (typeof value === "object") {
          return (
            <Text code style={{ wordBreak: "break-word", fontSize: "11px" }}>
              {JSON.stringify(value, null, 2)}
            </Text>
          );
        }
        return <Text style={{ wordBreak: "break-word" }}>{String(value)}</Text>;
      },
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      fixed: "right",
      render: (status) => {
        const config = {
          match: {
            icon: <CheckCircleOutlined />,
            color: "success",
            text: "Match",
          },
          mismatch: {
            icon: <CloseCircleOutlined />,
            color: "error",
            text: "Mismatch",
          },
          partial: {
            icon: <MinusCircleOutlined />,
            color: "warning",
            text: "Partial",
          },
        };

        const { icon, color, text } = config[status] || config.partial;

        return (
          <Tag icon={icon} color={color}>
            {text}
          </Tag>
        );
      },
      filters: [
        { text: "Match", value: "match" },
        { text: "Mismatch", value: "mismatch" },
        { text: "Partial", value: "partial" },
      ],
      onFilter: (value, record) => record.status === value,
    },
  ];

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          {/* Header with Document Selector */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ flex: 1 }}>
              <Title level={4} style={{ margin: 0, marginBottom: "8px" }}>
                Extracted Data
              </Title>
              <Text type="secondary">
                Compare extraction results with verified ground truth
              </Text>
            </div>
            <Space size="large">
              <div>
                <Text strong style={{ marginRight: "8px" }}>
                  Document:
                </Text>
                <Select
                  value={selectedDocId}
                  onChange={onSelectDocument}
                  style={{ width: 300 }}
                  placeholder="Select a document"
                  options={documents.map((doc) => ({
                    label: doc.original_filename,
                    value: doc.id,
                  }))}
                />
              </div>
              <Space>
                {extractedData && (
                  <Button
                    type="primary"
                    icon={<CheckCircleOutlined />}
                    onClick={async () => {
                      try {
                        await extractionApi.promoteToVerified(
                          projectId,
                          selectedDocId
                        );
                        showApiSuccess(
                          "Extracted data has been promoted to verified data"
                        );
                        loadData();
                      } catch (error) {
                        showApiError(
                          error,
                          "Failed to promote to verified data"
                        );
                      }
                    }}
                  >
                    {verifiedData
                      ? "Update Verified Data"
                      : "Promote to Verified Data"}
                  </Button>
                )}
                <Button icon={<ReloadOutlined />} onClick={loadData}>
                  Refresh
                </Button>
              </Space>
            </Space>
          </div>

          {/* Statistics Cards */}
          {extractedData && verifiedData && (
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="Overall Accuracy"
                    value={accuracy}
                    suffix="%"
                    valueStyle={{
                      color:
                        accuracy >= 90
                          ? "#3f8600"
                          : accuracy >= 70
                          ? "#faad14"
                          : "#cf1322",
                    }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="Total Fields"
                    value={totalFields}
                    prefix={<FileTextOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="Matched Fields"
                    value={matchedFields}
                    valueStyle={{ color: "#3f8600" }}
                    prefix={<CheckCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="Mismatched Fields"
                    value={mismatchedFields}
                    valueStyle={{ color: "#cf1322" }}
                    prefix={<CloseCircleOutlined />}
                  />
                </Card>
              </Col>
            </Row>
          )}

          {/* Info Alerts */}
          {!extractedData && !loading && (
            <Alert
              type="info"
              showIcon
              message="No extracted data for this document yet"
              description="Run extraction on this document from the Status tab to generate extracted data."
            />
          )}

          {extractedData && !verifiedData && (
            <Alert
              type="warning"
              showIcon
              message="No verified data available for comparison"
              description="Create verified data for this document in the Verified Data tab to enable field-level comparison."
            />
          )}

          {extractedData &&
            verifiedData &&
            comparison &&
            comparison.accuracy !== null &&
            comparison.accuracy !== undefined && (
              <Alert
                type="success"
                showIcon
                message={`Accuracy: ${Math.round(comparison.accuracy)}%`}
                description={`${comparison.matches || 0} out of ${
                  comparison.total_fields || 0
                } fields match the verified data.`}
              />
            )}

          {/* View Controls */}
          {extractedData && (
            <Space>
              <Text strong>View Mode:</Text>
              <Select
                value={viewMode}
                onChange={setViewMode}
                style={{ width: 150 }}
                options={[
                  {
                    label: "Data View",
                    value: "data",
                    icon: <FileTextOutlined />,
                  },
                  {
                    label: "JSON View",
                    value: "json",
                    icon: <CodeOutlined />,
                  },
                ]}
              />
              {viewMode === "data" && verifiedData && (
                <>
                  <Text strong style={{ marginLeft: "16px" }}>
                    Hide Empty:
                  </Text>
                  <Switch checked={hideEmpty} onChange={setHideEmpty} />
                  <Text strong style={{ marginLeft: "16px" }}>
                    Show Mismatch Only:
                  </Text>
                  <Switch
                    checked={showMismatchOnly}
                    onChange={setShowMismatchOnly}
                  />
                </>
              )}
            </Space>
          )}

          {/* Data Display */}
          {extractedData && (
            <>
              {viewMode === "data" && verifiedData ? (
                // Comparison Table View
                <Table
                  columns={columns}
                  dataSource={comparisonData}
                  rowKey="fieldPath"
                  pagination={{ pageSize: 20 }}
                  scroll={{ x: 1000 }}
                  size="small"
                  bordered
                />
              ) : viewMode === "data" && !verifiedData ? (
                // Simple data display without comparison
                <Card
                  type="inner"
                  title="Extracted Data (No Comparison Available)"
                >
                  <div
                    style={{ border: "1px solid #d9d9d9", borderRadius: "4px" }}
                  >
                    <MonacoEditor
                      height="50vh"
                      language="json"
                      value={JSON.stringify(extractedData.data || {}, null, 2)}
                      options={{
                        readOnly: true,
                        minimap: { enabled: false },
                        fontSize: 14,
                        lineNumbers: "on",
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                      }}
                      theme="vs-light"
                    />
                  </div>
                </Card>
              ) : (
                // JSON View
                <Tabs
                  defaultActiveKey="extracted"
                  items={[
                    {
                      key: "extracted",
                      label: "Extracted Data",
                      children: (
                        <div
                          style={{
                            border: "1px solid #d9d9d9",
                            borderRadius: "4px",
                          }}
                        >
                          <MonacoEditor
                            height="50vh"
                            language="json"
                            value={JSON.stringify(
                              extractedData.data || {},
                              null,
                              2
                            )}
                            options={{
                              readOnly: true,
                              minimap: { enabled: false },
                              fontSize: 14,
                              lineNumbers: "on",
                              scrollBeyondLastLine: false,
                              automaticLayout: true,
                            }}
                            theme="vs-light"
                          />
                        </div>
                      ),
                    },
                    verifiedData && {
                      key: "verified",
                      label: "Verified Data",
                      children: (
                        <div
                          style={{
                            border: "1px solid #d9d9d9",
                            borderRadius: "4px",
                          }}
                        >
                          <MonacoEditor
                            height="50vh"
                            language="json"
                            value={JSON.stringify(
                              verifiedData.data || {},
                              null,
                              2
                            )}
                            options={{
                              readOnly: true,
                              minimap: { enabled: false },
                              fontSize: 14,
                              lineNumbers: "on",
                              scrollBeyondLastLine: false,
                              automaticLayout: true,
                            }}
                            theme="vs-light"
                          />
                        </div>
                      ),
                    },
                  ].filter(Boolean)}
                />
              )}
            </>
          )}

          {/* Empty State */}
          {!extractedData && !loading && (
            <Empty
              description={
                <Space direction="vertical" size="large">
                  <Text>No extracted data for selected document</Text>
                  <Text type="secondary">
                    {selectedDocument
                      ? `Run extraction for "${selectedDocument.original_filename}" from the Status tab`
                      : "Select a document to view extracted data"}
                  </Text>
                </Space>
              }
            />
          )}

          {/* Document Info */}
          {selectedDocument && extractedData && (
            <Card size="small" type="inner" title="Document Information">
              <Space
                direction="vertical"
                size="small"
                style={{ width: "100%" }}
              >
                <div>
                  <Text strong>Filename: </Text>
                  <Text>{selectedDocument.original_filename}</Text>
                </div>
                <div>
                  <Text strong>Extracted At: </Text>
                  <Text>
                    {new Date(extractedData.created_at).toLocaleString()}
                  </Text>
                </div>
                {extractedData.prompt_id && (
                  <div>
                    <Text strong>Prompt ID: </Text>
                    <Text code>{extractedData.prompt_id}</Text>
                  </div>
                )}
              </Space>
            </Card>
          )}
        </Space>
      </Card>
    </div>
  );
}

ExtractedDataTab.propTypes = {
  projectId: PropTypes.string.isRequired,
  documents: PropTypes.array.isRequired,
  selectedDocId: PropTypes.string,
  onSelectDocument: PropTypes.func,
};

export default ExtractedDataTab;
