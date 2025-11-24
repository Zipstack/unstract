import { useState, useEffect } from "react";
import {
  Card,
  Typography,
  Space,
  Spin,
  Alert,
  Empty,
  Select,
  Tag,
  Modal,
  Table,
  Row,
  Col,
  Tooltip,
  Button,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  MinusCircleOutlined,
  FilterOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";

import {
  analyticsApi,
  extractionApi,
  showApiError,
} from "../../helpers/agentic-api";

const { Title, Text } = Typography;

// Color mapping for match status
const getStatusColor = (status) => {
  switch (status) {
    case "match":
      return "#52c41a"; // Green
    case "mismatch":
      return "#ff4d4f"; // Red
    case "partial":
      return "#faad14"; // Yellow/Orange
    default:
      return "#d9d9d9"; // Gray
  }
};

const getStatusText = (status) => {
  switch (status) {
    case "match":
      return "Match";
    case "mismatch":
      return "Mismatch";
    case "partial":
      return "Partial";
    default:
      return "N/A";
  }
};

const getStatusIcon = (status) => {
  switch (status) {
    case "match":
      return <CheckCircleOutlined />;
    case "mismatch":
      return <CloseCircleOutlined />;
    case "partial":
      return <MinusCircleOutlined />;
    default:
      return null;
  }
};

function MatrixTab({ projectId, documents }) {
  const [matrixData, setMatrixData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filteredDocuments, setFilteredDocuments] = useState([]);
  const [filteredFields, setFilteredFields] = useState([]);
  const [selectedDocumentFilter, setSelectedDocumentFilter] = useState(null);
  const [selectedFieldFilter, setSelectedFieldFilter] = useState(null);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [cellDetails, setCellDetails] = useState(null);
  const [cellDetailsLoading, setCellDetailsLoading] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadMatrixData();
    }
    // eslint-disable-next-line
  }, [projectId]);

  useEffect(() => {
    if (matrixData) {
      applyFilters();
    }
    // eslint-disable-next-line
  }, [matrixData, selectedDocumentFilter, selectedFieldFilter]);

  const loadMatrixData = async () => {
    try {
      setLoading(true);
      const data = await analyticsApi.getMismatchMatrix(projectId);
      console.log("Matrix API response:", data);
      console.log("Documents:", data?.documents);
      console.log("Fields:", data?.fields);
      console.log("Matrix:", data?.matrix);
      setMatrixData(data);
    } catch (error) {
      showApiError(error, "Failed to load matrix data");
      setMatrixData(null);
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = () => {
    if (!matrixData) return;

    // Backend returns "documents" but we also support legacy "docs"
    let docsData = matrixData.documents || matrixData.docs || [];
    let fieldsData = (matrixData.fields || []).map(
      (f) => f.field_path || f.path || f
    );

    // Apply document filter
    if (selectedDocumentFilter) {
      docsData = docsData.filter((doc) => doc.id === selectedDocumentFilter);
    }

    // Apply field filter
    if (selectedFieldFilter) {
      fieldsData = fieldsData.filter((field) => field === selectedFieldFilter);
    }

    setFilteredDocuments(docsData);
    setFilteredFields(fieldsData);
  };

  const handleCellClick = async (documentId, fieldPath) => {
    setDetailModalVisible(true);
    setCellDetailsLoading(true);

    try {
      // Fetch comparison details for this document and field
      const comparison = await extractionApi.getDocumentComparison(
        projectId,
        documentId
      );

      // Find the specific field in the comparison
      const fieldComparison = comparison.field_comparisons?.find(
        (fc) => fc.field_path === fieldPath
      );

      if (fieldComparison) {
        setCellDetails({
          document: documents.find((d) => d.id === documentId),
          fieldPath,
          extractedValue: fieldComparison.extracted_value,
          verifiedValue: fieldComparison.verified_value,
          status: fieldComparison.status,
          note: fieldComparison.note,
        });
      } else {
        // Fallback: load data manually
        const extracted = await extractionApi.getExtractedData(
          projectId,
          documentId
        );
        const verified = await extractionApi.getVerifiedData(
          projectId,
          documentId
        );

        // Navigate to nested field
        const getNestedValue = (obj, path) => {
          return path.split(".").reduce((acc, part) => acc?.[part], obj);
        };

        setCellDetails({
          document: documents.find((d) => d.id === documentId),
          fieldPath,
          extractedValue: getNestedValue(extracted?.data || {}, fieldPath),
          verifiedValue: getNestedValue(verified?.data || {}, fieldPath),
          status: "unknown",
        });
      }
    } catch (error) {
      console.error("Failed to load cell details:", error);
      setCellDetails(null);
    } finally {
      setCellDetailsLoading(false);
    }
  };

  const clearFilters = () => {
    setSelectedDocumentFilter(null);
    setSelectedFieldFilter(null);
  };

  // Backend returns "documents" but we also support legacy "docs"
  const docs = matrixData?.documents || matrixData?.docs || [];
  const fields = (matrixData?.fields || []).map(
    (f) => f.field_path || f.path || f
  );

  console.log(
    "MatrixTab render - loading:",
    loading,
    "docs:",
    docs,
    "fields:",
    fields,
    "matrixData:",
    matrixData
  );

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!matrixData || docs.length === 0) {
    return (
      <Card>
        <Empty
          description={
            <Space direction="vertical" size="large">
              <Text>No matrix data available</Text>
              <Text type="secondary">
                Run extractions and create verified data to generate the
                mismatch matrix
              </Text>
            </Space>
          }
        />
      </Card>
    );
  }

  // Use docs/fields if filteredDocuments/filteredFields are not yet populated
  const displayDocs = filteredDocuments.length > 0 ? filteredDocuments : docs;
  const displayFields = filteredFields.length > 0 ? filteredFields : fields;

  // Calculate statistics from matrix data
  const totalCells = displayDocs.length * displayFields.length;
  let matchCells = 0;
  let mismatchCells = 0;

  // Count matches and mismatches from the matrix
  displayDocs.forEach((doc) => {
    const docIdx = docs.findIndex((d) => d.id === doc.id);
    displayFields.forEach((field) => {
      const fieldIdx = fields.indexOf(field);
      const cellData = matrixData.matrix?.[docIdx]?.[fieldIdx];
      if (cellData) {
        if (cellData.match) {
          matchCells++;
        } else {
          mismatchCells++;
        }
      }
    });
  });

  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        {/* Header */}
        <Card>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <Title level={4} style={{ margin: 0, marginBottom: "8px" }}>
                Document-Field Mismatch Matrix
              </Title>
              <Text type="secondary">
                Heat map showing extraction accuracy across documents and fields
              </Text>
            </div>
            <Button icon={<ReloadOutlined />} onClick={loadMatrixData}>
              Refresh
            </Button>
          </div>
        </Card>

        {/* Filters */}
        <Card>
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
              <FilterOutlined style={{ fontSize: "16px" }} />
              <Text strong>Filters:</Text>
              <Space>
                <div>
                  <Text style={{ marginRight: "8px" }}>Document:</Text>
                  <Select
                    value={selectedDocumentFilter}
                    onChange={setSelectedDocumentFilter}
                    style={{ width: 250 }}
                    placeholder="All documents"
                    allowClear
                    options={[
                      { label: "All Documents", value: null },
                      ...docs.map((doc) => ({
                        label: doc.name,
                        value: doc.id,
                      })),
                    ]}
                  />
                </div>
                <div>
                  <Text style={{ marginRight: "8px" }}>Field:</Text>
                  <Select
                    value={selectedFieldFilter}
                    onChange={setSelectedFieldFilter}
                    style={{ width: 250 }}
                    placeholder="All fields"
                    allowClear
                    options={[
                      { label: "All Fields", value: null },
                      ...fields.map((field) => ({
                        label: field,
                        value: field,
                      })),
                    ]}
                  />
                </div>
                {(selectedDocumentFilter || selectedFieldFilter) && (
                  <Button onClick={clearFilters} size="small">
                    Clear All
                  </Button>
                )}
              </Space>
            </div>

            {/* Statistics */}
            <Row gutter={16}>
              <Col span={8}>
                <Alert
                  message="Total Cells"
                  description={totalCells}
                  type="info"
                  showIcon
                  icon={<InfoCircleOutlined />}
                />
              </Col>
              <Col span={8}>
                <Alert
                  message="Matches"
                  description={`${matchCells} (${
                    totalCells > 0
                      ? Math.round((matchCells / totalCells) * 100)
                      : 0
                  }%)`}
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                />
              </Col>
              <Col span={8}>
                <Alert
                  message="Mismatches"
                  description={`${mismatchCells} (${
                    totalCells > 0
                      ? Math.round((mismatchCells / totalCells) * 100)
                      : 0
                  }%)`}
                  type="error"
                  showIcon
                  icon={<CloseCircleOutlined />}
                />
              </Col>
            </Row>
          </Space>
        </Card>

        {/* Legend */}
        <Card title="Legend" size="small">
          <Space size="large">
            <Space>
              <div
                style={{
                  width: "20px",
                  height: "20px",
                  backgroundColor: getStatusColor("match"),
                  border: "1px solid #d9d9d9",
                }}
              />
              <Text>Match - Extracted value matches verified data</Text>
            </Space>
            <Space>
              <div
                style={{
                  width: "20px",
                  height: "20px",
                  backgroundColor: getStatusColor("partial"),
                  border: "1px solid #d9d9d9",
                }}
              />
              <Text>Partial - Close match or missing data</Text>
            </Space>
            <Space>
              <div
                style={{
                  width: "20px",
                  height: "20px",
                  backgroundColor: getStatusColor("mismatch"),
                  border: "1px solid #d9d9d9",
                }}
              />
              <Text>Mismatch - Extracted value does not match</Text>
            </Space>
            <Space>
              <div
                style={{
                  width: "20px",
                  height: "20px",
                  backgroundColor: getStatusColor("unknown"),
                  border: "1px solid #d9d9d9",
                }}
              />
              <Text>N/A - No data available</Text>
            </Space>
          </Space>
        </Card>

        {/* Matrix Heat Map */}
        <Card title="Heat Map">
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                borderCollapse: "collapse",
                width: "100%",
                minWidth: "800px",
              }}
            >
              <thead>
                <tr>
                  <th
                    style={{
                      border: "1px solid #d9d9d9",
                      padding: "12px",
                      backgroundColor: "#fafafa",
                      fontWeight: "bold",
                      position: "sticky",
                      left: 0,
                      zIndex: 2,
                    }}
                  >
                    Document / Field
                  </th>
                  {displayFields.map((field) => (
                    <th
                      key={field}
                      style={{
                        border: "1px solid #d9d9d9",
                        padding: "12px",
                        backgroundColor: "#fafafa",
                        fontWeight: "bold",
                        minWidth: "120px",
                        maxWidth: "200px",
                      }}
                    >
                      <Tooltip title={field}>
                        <Text
                          code
                          ellipsis
                          style={{
                            fontSize: "11px",
                            maxWidth: "180px",
                            display: "block",
                          }}
                        >
                          {field}
                        </Text>
                      </Tooltip>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayDocs.map((doc) => (
                  <tr key={doc.id}>
                    <td
                      style={{
                        border: "1px solid #d9d9d9",
                        padding: "12px",
                        backgroundColor: "#fafafa",
                        fontWeight: "500",
                        position: "sticky",
                        left: 0,
                        zIndex: 1,
                        maxWidth: "200px",
                      }}
                    >
                      <Tooltip title={doc.name}>
                        <Text
                          ellipsis
                          style={{
                            fontSize: "12px",
                            maxWidth: "180px",
                            display: "block",
                          }}
                        >
                          {doc.name}
                        </Text>
                      </Tooltip>
                    </td>
                    {displayFields.map((field) => {
                      // Get cell data from matrix array [doc_idx][field_idx]
                      const docIdx = docs.findIndex((d) => d.id === doc.id);
                      const actualFieldIdx = fields.indexOf(field);
                      const cellData =
                        matrixData.matrix?.[docIdx]?.[actualFieldIdx];

                      // Determine status from match field
                      let status = "unknown";
                      if (cellData) {
                        status = cellData.match ? "match" : "mismatch";
                      }
                      const color = getStatusColor(status);

                      return (
                        <td
                          key={`${doc.id}-${field}`}
                          style={{
                            border: "1px solid #d9d9d9",
                            padding: "8px",
                            backgroundColor: color,
                            textAlign: "center",
                            cursor: "pointer",
                            transition: "opacity 0.2s",
                          }}
                          onClick={() => handleCellClick(doc.id, field)}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.opacity = "0.7";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.opacity = "1";
                          }}
                        >
                          <Tooltip
                            title={`Click to view details: ${getStatusText(
                              status
                            )}`}
                          >
                            {getStatusIcon(status)}
                          </Tooltip>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </Space>

      {/* Cell Detail Modal */}
      <Modal
        title={
          <Space>
            <InfoCircleOutlined />
            <span>Field Comparison Details</span>
          </Space>
        }
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          <Button
            key="close"
            type="primary"
            onClick={() => setDetailModalVisible(false)}
          >
            Close
          </Button>,
        ]}
        width={800}
      >
        {cellDetailsLoading ? (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <Spin size="large" />
          </div>
        ) : cellDetails ? (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            {/* Document Info */}
            <Card size="small" type="inner" title="Document">
              <Text strong>
                {cellDetails.document?.original_filename || "Unknown"}
              </Text>
            </Card>

            {/* Field Info */}
            <Card size="small" type="inner" title="Field Path">
              <Text code>{cellDetails.fieldPath}</Text>
            </Card>

            {/* Comparison */}
            <Card size="small" type="inner" title="Comparison">
              <Table
                dataSource={[
                  {
                    key: "extracted",
                    label: "Extracted Value",
                    value: cellDetails.extractedValue,
                  },
                  {
                    key: "verified",
                    label: "Verified Value",
                    value: cellDetails.verifiedValue,
                  },
                ]}
                columns={[
                  {
                    title: "Type",
                    dataIndex: "label",
                    key: "label",
                    width: 200,
                    render: (text) => <Text strong>{text}</Text>,
                  },
                  {
                    title: "Value",
                    dataIndex: "value",
                    key: "value",
                    render: (value) => (
                      <Text style={{ wordBreak: "break-word" }}>
                        {value === null ? (
                          <Text type="secondary" italic>
                            null
                          </Text>
                        ) : (
                          String(value)
                        )}
                      </Text>
                    ),
                  },
                ]}
                pagination={false}
                size="small"
              />
            </Card>

            {/* Status */}
            <Card size="small" type="inner" title="Status">
              <Tag
                icon={getStatusIcon(cellDetails.status)}
                color={
                  cellDetails.status === "match"
                    ? "success"
                    : cellDetails.status === "mismatch"
                    ? "error"
                    : "warning"
                }
                style={{ fontSize: "14px", padding: "4px 12px" }}
              >
                {getStatusText(cellDetails.status)}
              </Tag>
            </Card>

            {/* Note if available */}
            {cellDetails.note && (
              <Card size="small" type="inner" title="Note">
                <Text>{cellDetails.note}</Text>
              </Card>
            )}
          </Space>
        ) : (
          <Empty description="No details available for this cell" />
        )}
      </Modal>
    </div>
  );
}

MatrixTab.propTypes = {
  projectId: PropTypes.string.isRequired,
  documents: PropTypes.array.isRequired,
};

export default MatrixTab;
