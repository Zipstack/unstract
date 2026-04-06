import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Card,
  Empty,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { ApiDeployments, ETLIcon, Task, Workflows } from "../../assets/index";
import { useDeploymentUsage } from "../../hooks/useMetricsData";

import "./MetricsDashboard.css";

const { Text } = Typography;

/**
 * Format large numbers with K/M/B suffixes.
 * Shows full value on hover via Tooltip.
 */
function formatCompactNumber(value) {
  const num = value || 0;
  if (num >= 1_000_000_000) {
    return `${(num / 1_000_000_000).toFixed(1)}B`;
  }
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`;
  }
  if (num >= 10_000) {
    return `${(num / 1_000).toFixed(1)}K`;
  }
  return num.toLocaleString();
}

const columns = [
  {
    title: "Deployment",
    dataIndex: "deployment_name",
    key: "deployment_name",
    ellipsis: true,
    render: (text) => <Text strong>{text}</Text>,
  },
  {
    title: (
      <span>
        Tokens{" "}
        <Tooltip title="Total LLM tokens consumed by this deployment">
          <InfoCircleOutlined className="llm-usage-info-icon" />
        </Tooltip>
      </span>
    ),
    dataIndex: "total_tokens",
    key: "total_tokens",
    sorter: (a, b) => a.total_tokens - b.total_tokens,
    defaultSortOrder: "descend",
    render: (value) => (
      <Tooltip title={(value || 0).toLocaleString()}>
        {formatCompactNumber(value)}
      </Tooltip>
    ),
    width: 120,
  },
  {
    title: "LLM Calls",
    dataIndex: "call_count",
    key: "call_count",
    sorter: (a, b) => a.call_count - b.call_count,
    render: (value) => (value || 0).toLocaleString(),
    width: 100,
  },
  {
    title: "Executions",
    dataIndex: "execution_count",
    key: "execution_count",
    sorter: (a, b) => a.execution_count - b.execution_count,
    render: (_, record) => {
      const total = record.execution_count || 0;
      const completed = record.completed_executions || 0;
      const failed = record.failed_executions || 0;
      return (
        <Tooltip
          title={`${completed.toLocaleString()} completed, ${failed.toLocaleString()} failed`}
        >
          <span className="execution-compact">
            <span>{total.toLocaleString()}</span>
            {completed > 0 && (
              <span className="execution-success">
                <CheckCircleOutlined /> {formatCompactNumber(completed)}
              </span>
            )}
            {failed > 0 && (
              <span className="execution-error">
                <CloseCircleOutlined /> {formatCompactNumber(failed)}
              </span>
            )}
          </span>
        </Tooltip>
      );
    },
    width: 170,
  },
  {
    title: "Pages",
    dataIndex: "total_pages_processed",
    key: "total_pages_processed",
    sorter: (a, b) =>
      (a.total_pages_processed || 0) - (b.total_pages_processed || 0),
    render: (value) => (value || 0).toLocaleString(),
    width: 100,
  },
  {
    title: "Cost",
    dataIndex: "total_cost",
    key: "total_cost",
    sorter: (a, b) => a.total_cost - b.total_cost,
    render: (value) => `$${(value || 0).toFixed(4)}`,
    width: 110,
  },
  {
    title: "Last Run",
    dataIndex: "last_execution_at",
    key: "last_execution_at",
    sorter: (a, b) =>
      (a.last_execution_at || "").localeCompare(b.last_execution_at || ""),
    render: (value) => (value ? value.split("T")[0] : "-"),
    width: 110,
  },
];

function DeploymentUsageTable({ startDate, endDate, refetchRef }) {
  const [activeType, setActiveType] = useState("API");

  const { data, loading, error, refetch } = useDeploymentUsage(
    activeType,
    startDate,
    endDate,
  );

  // Expose refetch to parent via ref
  useEffect(() => {
    if (refetchRef) {
      refetchRef.current = refetch;
    }
    return () => {
      if (refetchRef) {
        refetchRef.current = null;
      }
    };
  }, [refetch, refetchRef]);

  const handleTabChange = (key) => {
    setActiveType(key);
  };

  const deploymentTabs = [
    {
      key: "API",
      label: "API Deployments",
      icon: (
        <ApiDeployments
          className={`log-tab-icon ${activeType === "API" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "ETL",
      label: "ETL Pipelines",
      icon: (
        <ETLIcon
          className={`log-tab-icon ${activeType === "ETL" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "TASK",
      label: "Task Pipelines",
      icon: (
        <Task
          className={`log-tab-icon ${activeType === "TASK" ? "active" : ""}`}
        />
      ),
    },
    {
      key: "WF",
      label: "Workflows",
      icon: (
        <Workflows
          className={`log-tab-icon ${activeType === "WF" ? "active" : ""}`}
        />
      ),
    },
  ];

  const renderContent = () => {
    if (loading) {
      return (
        <div className="metrics-loading">
          <Spin />
        </div>
      );
    }

    if (error) {
      return (
        <Alert
          message="Failed to load usage data"
          description={error}
          type="error"
          showIcon
          className="llm-usage-error-alert"
        />
      );
    }

    if (!data?.deployments?.length) {
      return <Empty description="No LLM usage data for this period" />;
    }

    return (
      <Table
        dataSource={data.deployments}
        columns={columns}
        rowKey="deployment_id"
        size="middle"
        pagination={false}
        scroll={{ x: 900, y: 400 }}
        className="llm-usage-table"
      />
    );
  };

  return (
    <Card className="metrics-chart-card llm-usage-card">
      <div className="llm-usage-header">
        <Text strong className="llm-usage-title">
          Usage by Deployment
        </Text>
      </div>
      <Tabs
        items={deploymentTabs}
        activeKey={activeType}
        onChange={handleTabChange}
        size="small"
        className="deployment-type-tabs"
      />
      {data?.range_truncated && (
        <Text type="secondary" className="llm-usage-subtitle">
          Date range was limited to the last 30 days
        </Text>
      )}
      {renderContent()}
    </Card>
  );
}

DeploymentUsageTable.propTypes = {
  startDate: PropTypes.string,
  endDate: PropTypes.string,
  refetchRef: PropTypes.shape({ current: PropTypes.func }),
};

DeploymentUsageTable.defaultProps = {
  startDate: null,
  endDate: null,
  refetchRef: null,
};

export { DeploymentUsageTable };
