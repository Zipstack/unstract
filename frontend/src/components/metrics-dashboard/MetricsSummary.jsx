import { Card, Statistic, Row, Col, Spin, Empty } from "antd";
import PropTypes from "prop-types";
import {
  FileTextOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  RocketOutlined,
  DollarOutlined,
} from "@ant-design/icons";

import "./MetricsDashboard.css";

// Mapping metric names to display labels and icons
const METRIC_CONFIG = {
  documents_processed: {
    label: "Documents Processed",
    icon: <FileTextOutlined />,
    color: "#1890ff",
  },
  pages_processed: {
    label: "Pages Processed",
    icon: <FileTextOutlined />,
    color: "#52c41a",
  },
  prompt_executions: {
    label: "Prompt Executions",
    icon: <ThunderboltOutlined />,
    color: "#722ed1",
  },
  llm_calls: {
    label: "LLM Calls",
    icon: <ApiOutlined />,
    color: "#fa8c16",
  },
  challenges: {
    label: "Challenges",
    icon: <ThunderboltOutlined />,
    color: "#eb2f96",
  },
  summarization_calls: {
    label: "Summarizations",
    icon: <ThunderboltOutlined />,
    color: "#13c2c2",
  },
  deployed_api_requests: {
    label: "API Requests",
    icon: <RocketOutlined />,
    color: "#2f54eb",
  },
  etl_pipeline_executions: {
    label: "ETL Executions",
    icon: <RocketOutlined />,
    color: "#f5222d",
  },
  llm_usage: {
    label: "LLM Usage Cost",
    icon: <DollarOutlined />,
    color: "#faad14",
    prefix: "$",
    precision: 2,
  },
};

function MetricsSummary({ data, loading }) {
  if (loading) {
    return (
      <div className="metrics-loading">
        <Spin size="large" />
      </div>
    );
  }

  if (!data?.totals || data.totals.length === 0) {
    return (
      <Empty
        description="No metrics data available"
        className="metrics-empty"
      />
    );
  }

  return (
    <Row gutter={[16, 16]} className="metrics-summary">
      {data.totals.map((metric) => {
        const config = METRIC_CONFIG[metric.metric_name] || {
          label: metric.metric_name,
          icon: <ApiOutlined />,
          color: "#8c8c8c",
        };

        return (
          <Col xs={24} sm={12} md={8} lg={6} key={metric.metric_name}>
            <Card className="metric-card" bordered={false}>
              <Statistic
                title={
                  <span className="metric-title">
                    <span
                      className="metric-icon"
                      style={{ color: config.color }}
                    >
                      {config.icon}
                    </span>
                    {config.label}
                  </span>
                }
                value={metric.total_value || 0}
                precision={config.precision || 0}
                prefix={config.prefix}
                valueStyle={{ color: config.color }}
              />
              <div className="metric-count">
                {metric.total_count || 0} events
              </div>
            </Card>
          </Col>
        );
      })}
    </Row>
  );
}

MetricsSummary.propTypes = {
  data: PropTypes.shape({
    totals: PropTypes.arrayOf(
      PropTypes.shape({
        metric_name: PropTypes.string.isRequired,
        total_value: PropTypes.number,
        total_count: PropTypes.number,
      })
    ),
  }),
  loading: PropTypes.bool,
};

MetricsSummary.defaultProps = {
  data: null,
  loading: false,
};

export { MetricsSummary };
