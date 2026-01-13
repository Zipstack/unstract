import { Table, Tag } from "antd";
import PropTypes from "prop-types";
import { useMemo } from "react";

import "./MetricsDashboard.css";

// Color mapping for metric types
const METRIC_TYPE_COLORS = {
  counter: "blue",
  histogram: "green",
};

function MetricsTable({ data, loading }) {
  const columns = useMemo(
    () => [
      {
        title: "Metric",
        dataIndex: "metric_name",
        key: "metric_name",
        render: (text) => (
          <span className="metric-name-cell">
            {text.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </span>
        ),
        sorter: (a, b) => a.metric_name.localeCompare(b.metric_name),
      },
      {
        title: "Type",
        dataIndex: "metric_type",
        key: "metric_type",
        render: (type) => (
          <Tag color={METRIC_TYPE_COLORS[type] || "default"}>{type}</Tag>
        ),
        filters: [
          { text: "Counter", value: "counter" },
          { text: "Histogram", value: "histogram" },
        ],
        onFilter: (value, record) => record.metric_type === value,
      },
      {
        title: "Total Value",
        dataIndex: "total_value",
        key: "total_value",
        render: (value) => value?.toLocaleString() || "0",
        sorter: (a, b) => (a.total_value || 0) - (b.total_value || 0),
        align: "right",
      },
      {
        title: "Event Count",
        dataIndex: "total_count",
        key: "total_count",
        render: (count) => count?.toLocaleString() || "0",
        sorter: (a, b) => (a.total_count || 0) - (b.total_count || 0),
        align: "right",
      },
      {
        title: "Avg Value",
        dataIndex: "average_value",
        key: "average_value",
        render: (value) => (value ? value.toFixed(2) : "-"),
        sorter: (a, b) => (a.average_value || 0) - (b.average_value || 0),
        align: "right",
      },
      {
        title: "Min",
        dataIndex: "min_value",
        key: "min_value",
        render: (value) => (value !== undefined ? value.toFixed(2) : "-"),
        align: "right",
      },
      {
        title: "Max",
        dataIndex: "max_value",
        key: "max_value",
        render: (value) => (value !== undefined ? value.toFixed(2) : "-"),
        align: "right",
      },
    ],
    []
  );

  const tableData = useMemo(() => {
    if (!data?.summary) return [];
    return data.summary.map((item, index) => ({
      ...item,
      key: item.metric_name || index,
    }));
  }, [data]);

  return (
    <Table
      columns={columns}
      dataSource={tableData}
      loading={loading}
      pagination={{ pageSize: 10 }}
      size="middle"
      className="metrics-table"
      scroll={{ x: 800 }}
    />
  );
}

MetricsTable.propTypes = {
  data: PropTypes.shape({
    summary: PropTypes.arrayOf(
      PropTypes.shape({
        metric_name: PropTypes.string.isRequired,
        metric_type: PropTypes.string,
        total_value: PropTypes.number,
        total_count: PropTypes.number,
        average_value: PropTypes.number,
        min_value: PropTypes.number,
        max_value: PropTypes.number,
      })
    ),
  }),
  loading: PropTypes.bool,
};

MetricsTable.defaultProps = {
  data: null,
  loading: false,
};

export { MetricsTable };
