import { useState, useEffect } from "react";
import {
  Table,
  Tag,
  Typography,
  Space,
  Button,
  Statistic,
  Card,
  Row,
  Col,
  Progress,
  Tooltip,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./ExecutionHistoryTab.css";

const { Title, Text } = Typography;

export function ExecutionHistoryTab({ project }) {
  const [executions, setExecutions] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    fetchExecutions();
    fetchStatistics();
  }, [project.id]);

  const fetchExecutions = async () => {
    setLoading(true);
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/execution-audits/`,
        {
          params: { lookup_project_id: project.id },
        }
      );
      setExecutions(response.data.results || []);
    } catch (error) {
      setAlertDetails({
        type: "error",
        content: "Failed to fetch execution history",
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchStatistics = async () => {
    try {
      const response = await axiosPrivate.get(
        `/api/v1/unstract/${sessionDetails?.orgId}/lookup/execution-audits/statistics/`,
        {
          params: { lookup_project_id: project.id },
        }
      );
      setStatistics(response.data);
    } catch (error) {
      console.error("Failed to fetch statistics:", error);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchExecutions(), fetchStatistics()]);
    setRefreshing(false);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "success":
        return <CheckCircleOutlined style={{ color: "#52c41a" }} />;
      case "failure":
        return <CloseCircleOutlined style={{ color: "#f5222d" }} />;
      case "partial":
        return <ClockCircleOutlined style={{ color: "#faad14" }} />;
      default:
        return null;
    }
  };

  const columns = [
    {
      title: "Execution ID",
      dataIndex: "execution_id",
      key: "execution_id",
      render: (id) => (
        <Tooltip title={id}>
          <Text code>{id.substring(0, 8)}...</Text>
        </Tooltip>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status) => (
        <Space>
          {getStatusIcon(status)}
          <Tag
            color={
              status === "success"
                ? "green"
                : status === "failure"
                ? "red"
                : "orange"
            }
          >
            {status.toUpperCase()}
          </Tag>
        </Space>
      ),
    },
    {
      title: "Confidence",
      dataIndex: "confidence_score",
      key: "confidence_score",
      render: (score) => {
        if (!score) return "-";
        const percent = Math.round(score * 100);
        return (
          <Progress
            percent={percent}
            size="small"
            strokeColor={
              percent >= 80 ? "#52c41a" : percent >= 60 ? "#faad14" : "#f5222d"
            }
            style={{ width: 80 }}
          />
        );
      },
    },
    {
      title: "Execution Time",
      dataIndex: "execution_time_ms",
      key: "execution_time_ms",
      render: (time) => (time ? `${time}ms` : "-"),
    },
    {
      title: "Cache Hit",
      dataIndex: "llm_response_cached",
      key: "llm_response_cached",
      render: (cached) => (
        <Tag color={cached ? "green" : "default"}>
          {cached ? "Cached" : "Fresh"}
        </Tag>
      ),
    },
    {
      title: "Executed At",
      dataIndex: "executed_at",
      key: "executed_at",
      render: (date) => new Date(date).toLocaleString(),
    },
    {
      title: "Error",
      dataIndex: "error_message",
      key: "error_message",
      render: (error) =>
        error ? (
          <Tooltip title={error}>
            <Text type="danger" ellipsis style={{ maxWidth: 150 }}>
              {error}
            </Text>
          </Tooltip>
        ) : (
          "-"
        ),
    },
  ];

  return (
    <div className="execution-history-tab">
      <div className="tab-header">
        <div>
          <Title level={4}>Execution History</Title>
          <Text type="secondary">
            View past Look-Up executions and statistics
          </Text>
        </div>
        <Button
          icon={<SyncOutlined />}
          onClick={handleRefresh}
          loading={refreshing}
        >
          Refresh
        </Button>
      </div>

      {statistics && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card>
              <Statistic
                title="Total Executions"
                value={statistics.total_executions || 0}
                prefix={<DatabaseOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Success Rate"
                value={Math.round((statistics.success_rate || 0) * 100)}
                suffix="%"
                prefix={<CheckCircleOutlined />}
                valueStyle={{
                  color:
                    statistics.success_rate >= 0.9
                      ? "#52c41a"
                      : statistics.success_rate >= 0.7
                      ? "#faad14"
                      : "#f5222d",
                }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Avg Execution Time"
                value={Math.round(statistics.avg_execution_time_ms || 0)}
                suffix="ms"
                prefix={<ThunderboltOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="Cache Hit Rate"
                value={Math.round((statistics.cache_hit_rate || 0) * 100)}
                suffix="%"
                prefix={<DatabaseOutlined />}
                valueStyle={{
                  color:
                    statistics.cache_hit_rate >= 0.5 ? "#52c41a" : "#1890ff",
                }}
              />
            </Card>
          </Col>
        </Row>
      )}

      <Table
        columns={columns}
        dataSource={executions}
        loading={loading}
        rowKey="id"
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `Total ${total} executions`,
        }}
      />
    </div>
  );
}

ExecutionHistoryTab.propTypes = {
  project: PropTypes.shape({
    id: PropTypes.string.isRequired,
  }).isRequired,
};
