import { useState, useEffect } from "react";
import {
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Typography,
  Space,
  Spin,
  Alert,
  Progress,
  Empty,
  Button,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  BarChartOutlined,
  FileTextOutlined,
  WarningOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";

import {
  analyticsApi,
  showApiError,
  showApiSuccess,
} from "../../helpers/agentic-api";

const { Title, Text } = Typography;

function AnalyticsTab({ projectId }) {
  const [summary, setSummary] = useState(null);
  const [topMismatched, setTopMismatched] = useState([]);
  const [errorTypes, setErrorTypes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [populating, setPopulating] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadAnalytics();
    }
  }, [projectId]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);

      // Load all analytics data
      const [summaryData, topMismatchedData, errorTypesData] =
        await Promise.all([
          analyticsApi.getSummary(projectId).catch(() => null),
          analyticsApi.getTopMismatchedFields(projectId, 20).catch(() => []),
          analyticsApi.getErrorTypeDistribution(projectId).catch(() => []),
        ]);

      setSummary(summaryData);
      // Ensure arrays are always arrays
      setTopMismatched(
        Array.isArray(topMismatchedData) ? topMismatchedData : []
      );
      setErrorTypes(Array.isArray(errorTypesData) ? errorTypesData : []);
    } catch (error) {
      showApiError(error, "Failed to load analytics data");
    } finally {
      setLoading(false);
    }
  };

  const handlePopulateAnalytics = async () => {
    try {
      setPopulating(true);
      message.loading("Populating analytics data...", 0);

      const result = await analyticsApi.populateAnalytics(projectId, false);

      message.destroy();

      if (result.documents_processed > 0) {
        showApiSuccess(
          `Successfully processed ${result.documents_processed} documents with ${result.overall_accuracy}% accuracy`,
          "Analytics Populated"
        );
        // Reload analytics data
        loadAnalytics();
      } else {
        message.info(result.message || "No documents available for comparison");
      }
    } catch (error) {
      message.destroy();
      showApiError(error, "Failed to populate analytics");
    } finally {
      setPopulating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!summary) {
    return (
      <Card>
        <Empty
          description={
            <Space direction="vertical" size="large">
              <Text>No analytics data available</Text>
              <Text type="secondary">
                Run extractions and create verified data to generate analytics
              </Text>
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handlePopulateAnalytics}
                loading={populating}
                style={{ marginTop: "16px" }}
              >
                Populate Analytics
              </Button>
            </Space>
          }
        />
      </Card>
    );
  }

  // Columns for top mismatched fields table
  const mismatchedColumns = [
    {
      title: "Field Path",
      dataIndex: "field_path",
      key: "field_path",
      render: (text) => (
        <Text code style={{ fontSize: "12px" }}>
          {text}
        </Text>
      ),
    },
    {
      title: "Accuracy",
      dataIndex: "accuracy",
      key: "accuracy",
      width: 200,
      render: (accuracy) => {
        const value = Math.round(accuracy);
        let color = "#cf1322";
        if (value >= 90) color = "#3f8600";
        else if (value >= 70) color = "#faad14";

        return (
          <Space>
            <Progress
              percent={value}
              size="small"
              strokeColor={color}
              style={{ width: 100 }}
            />
            <Text>{value}%</Text>
          </Space>
        );
      },
      sorter: (a, b) => a.accuracy - b.accuracy,
    },
    {
      title: "Incorrect Count",
      dataIndex: "incorrect",
      key: "incorrect",
      width: 150,
      render: (count) => (
        <Tag color="error" icon={<CloseCircleOutlined />}>
          {count}
        </Tag>
      ),
      sorter: (a, b) => a.incorrect - b.incorrect,
    },
    {
      title: "Common Error",
      dataIndex: "common_error",
      key: "common_error",
      render: (error) => (
        <Text type="secondary" style={{ fontSize: "12px" }}>
          {error || "N/A"}
        </Text>
      ),
    },
  ];

  // Columns for error types table
  const errorTypesColumns = [
    {
      title: "Error Type",
      dataIndex: "error_type",
      key: "error_type",
      render: (text) => <Tag color="orange">{text || "Unknown"}</Tag>,
    },
    {
      title: "Count",
      dataIndex: "count",
      key: "count",
      width: 150,
      render: (count) => (
        <Tag color="red" icon={<WarningOutlined />}>
          {count}
        </Tag>
      ),
      sorter: (a, b) => a.count - b.count,
      defaultSortOrder: "descend",
    },
  ];

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
                Project Analytics
              </Title>
              <Text type="secondary">
                Overall extraction performance and accuracy metrics
              </Text>
            </div>
            <Button
              type="default"
              icon={<ReloadOutlined />}
              onClick={handlePopulateAnalytics}
              loading={populating}
            >
              Refresh Analytics
            </Button>
          </div>
        </Card>

        {/* Summary Statistics */}
        <Row gutter={16}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Overall Accuracy"
                value={Math.round(summary.overall_accuracy || 0)}
                suffix="%"
                valueStyle={{
                  color:
                    summary.overall_accuracy >= 90
                      ? "#3f8600"
                      : summary.overall_accuracy >= 70
                      ? "#faad14"
                      : "#cf1322",
                }}
                prefix={<BarChartOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Total Documents"
                value={summary.total_docs || 0}
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Matched Fields"
                value={summary.matched_fields || 0}
                valueStyle={{ color: "#3f8600" }}
                prefix={<CheckCircleOutlined />}
              />
              <Text type="secondary" style={{ fontSize: "12px" }}>
                out of {summary.total_fields || 0} total fields
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Failed Fields"
                value={summary.failed_fields || 0}
                valueStyle={{ color: "#cf1322" }}
                prefix={<CloseCircleOutlined />}
              />
              <Text type="secondary" style={{ fontSize: "12px" }}>
                {summary.total_fields > 0
                  ? `${Math.round(
                      (summary.failed_fields / summary.total_fields) * 100
                    )}% failure rate`
                  : "0% failure rate"}
              </Text>
            </Card>
          </Col>
        </Row>

        {/* Info Alert */}
        {summary.total_docs === 0 && (
          <Alert
            type="info"
            showIcon
            message="No documents analyzed yet"
            description="Upload documents and run extractions with verified data to see analytics."
          />
        )}

        {summary.overall_accuracy < 70 && summary.total_docs > 0 && (
          <Alert
            type="warning"
            showIcon
            message="Low overall accuracy detected"
            description="Consider tuning your prompts or reviewing the top mismatched fields below to improve accuracy."
          />
        )}

        {/* Top Mismatched Fields */}
        {topMismatched.length > 0 && (
          <Card
            title={
              <Space>
                <WarningOutlined style={{ color: "#faad14" }} />
                <Text strong>Top Mismatched Fields</Text>
              </Space>
            }
          >
            <Table
              columns={mismatchedColumns}
              dataSource={topMismatched}
              rowKey="field_path"
              pagination={{ pageSize: 10 }}
              size="small"
            />
          </Card>
        )}

        {/* Error Types Distribution */}
        {errorTypes.length > 0 && (
          <Card
            title={
              <Space>
                <CloseCircleOutlined style={{ color: "#cf1322" }} />
                <Text strong>Error Type Distribution</Text>
              </Space>
            }
          >
            <Table
              columns={errorTypesColumns}
              dataSource={errorTypes}
              rowKey="error_type"
              pagination={false}
              size="small"
            />
          </Card>
        )}

        {/* Accuracy Breakdown */}
        <Card title="Accuracy Breakdown">
          <Row gutter={16}>
            <Col span={8}>
              <Card size="small" style={{ background: "#f6ffed" }}>
                <Statistic
                  title="High Accuracy (90-100%)"
                  value={
                    topMismatched.length > 0
                      ? topMismatched.filter((f) => f.accuracy >= 90).length
                      : summary.matched_fields > 0
                      ? summary.total_fields
                      : 0
                  }
                  suffix={`/ ${
                    topMismatched.length > 0
                      ? topMismatched.length
                      : summary.total_fields || 0
                  }`}
                  valueStyle={{ color: "#3f8600" }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ background: "#fffbe6" }}>
                <Statistic
                  title="Medium Accuracy (70-89%)"
                  value={
                    topMismatched.filter(
                      (f) => f.accuracy >= 70 && f.accuracy < 90
                    ).length
                  }
                  suffix={`/ ${
                    topMismatched.length > 0
                      ? topMismatched.length
                      : summary.total_fields || 0
                  }`}
                  valueStyle={{ color: "#faad14" }}
                />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ background: "#fff1f0" }}>
                <Statistic
                  title="Low Accuracy (<70%)"
                  value={topMismatched.filter((f) => f.accuracy < 70).length}
                  suffix={`/ ${
                    topMismatched.length > 0
                      ? topMismatched.length
                      : summary.total_fields || 0
                  }`}
                  valueStyle={{ color: "#cf1322" }}
                />
              </Card>
            </Col>
          </Row>
        </Card>

        {/* Recommendations */}
        {summary.overall_accuracy < 90 && topMismatched.length > 0 && (
          <Card
            title={
              <Space>
                <BarChartOutlined />
                <Text strong>Recommendations</Text>
              </Space>
            }
          >
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              {topMismatched.slice(0, 3).map((field) => (
                <Alert
                  key={field.field_path}
                  type="info"
                  showIcon
                  message={`Improve "${field.field_path}" extraction`}
                  description={
                    <div>
                      <Text>
                        Current accuracy: {Math.round(field.accuracy)}% (
                        {field.incorrect} incorrect)
                      </Text>
                      <br />
                      <Text type="secondary">
                        Consider using the &quot;Tune&quot; feature in the
                        Prompt tab to optimize this field&apos;s extraction.
                      </Text>
                    </div>
                  }
                />
              ))}
            </Space>
          </Card>
        )}
      </Space>
    </div>
  );
}

AnalyticsTab.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export default AnalyticsTab;
