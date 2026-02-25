import { Table, Card, Empty, Spin, Typography, Tooltip, Button } from "antd";
import { InfoCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";

import "./MetricsDashboard.css";

const { Text } = Typography;

const columns = [
  {
    title: "Workflow",
    dataIndex: "workflow_name",
    key: "workflow_name",
    ellipsis: true,
    render: (text) => <Text strong>{text}</Text>,
  },
  {
    title: (
      <span>
        Tokens{" "}
        <Tooltip title="Total LLM tokens consumed by this workflow">
          <InfoCircleOutlined style={{ color: "#8c8c8c", fontSize: 12 }} />
        </Tooltip>
      </span>
    ),
    dataIndex: "total_tokens",
    key: "total_tokens",
    sorter: (a, b) => a.total_tokens - b.total_tokens,
    defaultSortOrder: "descend",
    render: (value) => (value || 0).toLocaleString(),
    width: 140,
  },
  {
    title: "LLM Calls",
    dataIndex: "call_count",
    key: "call_count",
    sorter: (a, b) => a.call_count - b.call_count,
    render: (value) => (value || 0).toLocaleString(),
    width: 120,
  },
  {
    title: "Cost",
    dataIndex: "total_cost",
    key: "total_cost",
    sorter: (a, b) => a.total_cost - b.total_cost,
    render: (value) => `$${(value || 0).toFixed(4)}`,
    width: 120,
  },
];

function LLMUsageTable({ data, loading, onRefresh }) {
  const refreshButton = onRefresh ? (
    <Tooltip title="Refresh (bypasses cache)">
      <Button
        icon={<ReloadOutlined />}
        size="small"
        onClick={onRefresh}
        loading={loading}
      />
    </Tooltip>
  ) : null;

  if (loading) {
    return (
      <Card className="metrics-chart-card llm-usage-card">
        <div className="llm-usage-header">
          <Text strong className="llm-usage-title">
            LLM Usage by Workflow
          </Text>
          {refreshButton}
        </div>
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!data?.workflows?.length) {
    return (
      <Card className="metrics-chart-card llm-usage-card">
        <div className="llm-usage-header">
          <Text strong className="llm-usage-title">
            LLM Usage by Workflow
          </Text>
          {refreshButton}
        </div>
        <Empty description="No LLM usage data for this period" />
      </Card>
    );
  }

  return (
    <Card className="metrics-chart-card llm-usage-card">
      <div className="llm-usage-header">
        <Text strong className="llm-usage-title">
          LLM Usage by Workflow
        </Text>
        {refreshButton}
      </div>
      <Table
        dataSource={data.workflows}
        columns={columns}
        rowKey="workflow_id"
        size="middle"
        pagination={false}
        scroll={{ y: 400 }}
        className="llm-usage-table"
      />
    </Card>
  );
}

LLMUsageTable.propTypes = {
  data: PropTypes.shape({
    workflows: PropTypes.arrayOf(
      PropTypes.shape({
        workflow_id: PropTypes.string.isRequired,
        workflow_name: PropTypes.string.isRequired,
        total_tokens: PropTypes.number,
        total_cost: PropTypes.number,
        call_count: PropTypes.number,
      })
    ),
  }),
  loading: PropTypes.bool,
  onRefresh: PropTypes.func,
};

LLMUsageTable.defaultProps = {
  data: null,
  loading: false,
  onRefresh: null,
};

export { LLMUsageTable };
