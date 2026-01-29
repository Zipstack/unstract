import { Row, Col, Spin, Empty } from "antd";
import PropTypes from "prop-types";
import {
  FileTextOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  RocketOutlined,
  DollarOutlined,
  WarningOutlined,
} from "@ant-design/icons";

import "./MetricsDashboard.css";

// Mapping metric names to display config with colors matching reference design
const METRIC_CONFIG = {
  pages_processed: {
    label: "Total Pages Processed",
    icon: <FileTextOutlined />,
    bgColor: "#e8f5e9",
    iconBg: "#c8e6c9",
    iconColor: "#2e7d32",
    suffix: "pages",
  },
  documents_processed: {
    label: "Documents Processed",
    icon: <FileTextOutlined />,
    bgColor: "#fff3e0",
    iconBg: "#ffe0b2",
    iconColor: "#e65100",
    suffix: "docs",
  },
  llm_calls: {
    label: "LLM Calls",
    icon: <ApiOutlined />,
    bgColor: "#e0f2f1",
    iconBg: "#b2dfdb",
    iconColor: "#00695c",
    suffix: "",
  },
  prompt_executions: {
    label: "Prompt Executions",
    icon: <ThunderboltOutlined />,
    bgColor: "#ede7f6",
    iconBg: "#d1c4e9",
    iconColor: "#4527a0",
    suffix: "",
  },
  deployed_api_requests: {
    label: "API Requests",
    icon: <RocketOutlined />,
    bgColor: "#e3f2fd",
    iconBg: "#bbdefb",
    iconColor: "#1565c0",
    suffix: "",
  },
  llm_usage: {
    label: "LLM Usage Cost",
    icon: <DollarOutlined />,
    bgColor: "#fce4ec",
    iconBg: "#f8bbd9",
    iconColor: "#c2185b",
    prefix: "$",
    precision: 2,
    suffix: "",
  },
  etl_pipeline_executions: {
    label: "ETL Executions",
    icon: <RocketOutlined />,
    bgColor: "#ffebee",
    iconBg: "#ffcdd2",
    iconColor: "#c62828",
    suffix: "",
  },
  challenges: {
    label: "Challenges",
    icon: <ThunderboltOutlined />,
    bgColor: "#fce4ec",
    iconBg: "#f8bbd9",
    iconColor: "#ad1457",
    suffix: "",
  },
  summarization_calls: {
    label: "Summarizations",
    icon: <ThunderboltOutlined />,
    bgColor: "#e0f7fa",
    iconBg: "#b2ebf2",
    iconColor: "#00838f",
    suffix: "",
  },
  failed_pages: {
    label: "Failed Pages",
    icon: <WarningOutlined />,
    bgColor: "#fff1f0",
    iconBg: "#ffccc7",
    iconColor: "#cf1322",
    suffix: "pages",
  },
};

// Priority order for displaying metrics (show top 4 first like reference)
const METRIC_PRIORITY = [
  "pages_processed",
  "documents_processed",
  "failed_pages",
  "llm_calls",
  "prompt_executions",
  "deployed_api_requests",
  "llm_usage",
];

/**
 * Format large numbers for display.
 *
 * @param {number} value - The number to format
 * @param {number} precision - Decimal precision (default 0)
 * @return {string} Formatted number string
 */
function formatValue(value, precision = 0) {
  if (value === null || value === undefined) return "0";
  if (precision > 0) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    });
  }
  return value.toLocaleString();
}

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

  // Sort metrics by priority and take top ones
  const sortedMetrics = [...data.totals].sort((a, b) => {
    const aIndex = METRIC_PRIORITY.indexOf(a.metric_name);
    const bIndex = METRIC_PRIORITY.indexOf(b.metric_name);
    if (aIndex === -1 && bIndex === -1) return 0;
    if (aIndex === -1) return 1;
    if (bIndex === -1) return -1;
    return aIndex - bIndex;
  });

  return (
    <Row gutter={[16, 16]} className="metrics-summary">
      {sortedMetrics.map((metric) => {
        const config = METRIC_CONFIG[metric.metric_name] || {
          label: metric.metric_name,
          icon: <ApiOutlined />,
          bgColor: "#f5f5f5",
          iconBg: "#e0e0e0",
          iconColor: "#616161",
          suffix: "",
        };

        const displayValue = formatValue(
          metric.total_value || 0,
          config.precision || 0
        );

        return (
          <Col xs={24} sm={12} md={8} lg={6} key={metric.metric_name}>
            <div
              className="summary-card"
              style={{ backgroundColor: config.bgColor }}
            >
              <div
                className="summary-card-icon"
                style={{ backgroundColor: config.iconBg }}
              >
                <span style={{ color: config.iconColor }}>{config.icon}</span>
              </div>
              <div className="summary-card-content">
                <div className="summary-card-label">{config.label}</div>
                <div className="summary-card-value">
                  {config.prefix}
                  {displayValue}
                  {config.suffix && (
                    <span className="summary-card-suffix">
                      {" "}
                      {config.suffix}
                    </span>
                  )}
                </div>
              </div>
            </div>
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
