import {
  CircleCheck,
  DollarSign,
  Eye,
  FileText,
  Plug,
  Rocket,
  TriangleAlert,
  Zap,
} from "lucide-react";
import PropTypes from "prop-types";
import { Col, Row } from "@/components/ui/shims/antd-layout";
import { Empty, Spin } from "@/components/ui/shims/antd-leaves";

import "./MetricsDashboard.css";

// Mapping metric names to display config with colors matching reference design
const METRIC_CONFIG = {
  pages_processed: {
    label: "Pages Processed",
    icon: <FileText />,
    bgColor: "#e8f5e9",
    iconBg: "#c8e6c9",
    iconColor: "#2e7d32",
    suffix: "",
  },
  documents_processed: {
    label: "Documents Processed",
    icon: <FileText />,
    bgColor: "#fff3e0",
    iconBg: "#ffe0b2",
    iconColor: "#e65100",
    suffix: "",
  },
  llm_calls: {
    label: "LLM Calls",
    icon: <Plug />,
    bgColor: "#e0f2f1",
    iconBg: "#b2dfdb",
    iconColor: "#00695c",
    suffix: "",
  },
  prompt_executions: {
    label: "Prompt Executions",
    icon: <Zap />,
    bgColor: "#ede7f6",
    iconBg: "#d1c4e9",
    iconColor: "#4527a0",
    suffix: "",
  },
  deployed_api_requests: {
    label: "API Requests",
    icon: <Rocket />,
    bgColor: "#e3f2fd",
    iconBg: "#bbdefb",
    iconColor: "#1565c0",
    suffix: "",
  },
  llm_usage: {
    label: "LLM Usage Cost",
    icon: <DollarSign />,
    bgColor: "#fce4ec",
    iconBg: "#f8bbd9",
    iconColor: "#c2185b",
    prefix: "$",
    precision: 2,
    suffix: "",
  },
  etl_pipeline_executions: {
    label: "ETL Executions",
    icon: <Rocket />,
    bgColor: "#ffebee",
    iconBg: "#ffcdd2",
    iconColor: "#c62828",
    suffix: "",
  },
  challenges: {
    label: "Challenges",
    icon: <Zap />,
    bgColor: "#fce4ec",
    iconBg: "#f8bbd9",
    iconColor: "#ad1457",
    suffix: "",
  },
  summarization_calls: {
    label: "Summarizations",
    icon: <Zap />,
    bgColor: "#e0f7fa",
    iconBg: "#b2ebf2",
    iconColor: "#00838f",
    suffix: "",
  },
  failed_pages: {
    label: "Failed Pages",
    icon: <TriangleAlert />,
    bgColor: "#fff1f0",
    iconBg: "#ffccc7",
    iconColor: "#cf1322",
    suffix: "",
  },
  hitl_reviews: {
    label: "HITL Reviews",
    icon: <Eye />,
    bgColor: "#f3e8ff",
    iconBg: "#e0cffc",
    iconColor: "#6d28d9",
    suffix: "",
  },
  hitl_completions: {
    label: "HITL Completions",
    icon: <CircleCheck />,
    bgColor: "#ecfdf5",
    iconBg: "#d1fae5",
    iconColor: "#059669",
    suffix: "",
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
  "hitl_reviews",
  "hitl_completions",
];

/**
 * Format large numbers for display.
 *
 * @param {number|null|undefined} value - The number to format
 * @param {number} precision - Decimal precision (default 0)
 * @return {string} Formatted number string
 */
function formatValue(value, precision = 0) {
  if (value == null) {
    return "0";
  }
  if (precision > 0) {
    return value.toLocaleString(undefined, {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    });
  }
  return Math.round(value).toLocaleString();
}

function MetricsSummary({ data = null, loading = false }) {
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

  // Sort metrics by priority, skip zero-value metrics
  const sortedMetrics = [...data.totals]
    .filter((m) => m.total_value > 0)
    .sort((a, b) => {
      const aIndex = METRIC_PRIORITY.indexOf(a.metric_name);
      const bIndex = METRIC_PRIORITY.indexOf(b.metric_name);
      if (aIndex === -1 && bIndex === -1) {
        return 0;
      }
      if (aIndex === -1) {
        return 1;
      }
      if (bIndex === -1) {
        return -1;
      }
      return aIndex - bIndex;
    });

  return (
    <Row gutter={[16, 16]} className="metrics-summary">
      {sortedMetrics.map((metric) => {
        const config = METRIC_CONFIG[metric.metric_name] || {
          label: metric.metric_name,
          icon: <Plug />,
          bgColor: "#f5f5f5",
          iconBg: "#e0e0e0",
          iconColor: "#616161",
          suffix: "",
        };

        const displayValue = formatValue(
          metric.total_value || 0,
          config.precision || 0,
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
      }),
    ),
  }),
  loading: PropTypes.bool,
};

export { MetricsSummary };
