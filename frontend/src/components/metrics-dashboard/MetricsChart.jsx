import { FilterOutlined } from "@ant-design/icons";
import { Button, Card, Dropdown, Empty, Spin } from "antd";
import PropTypes from "prop-types";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import "./MetricsDashboard.css";

// Colors for chart lines
const TREND_COLORS = [
  "#1890ff",
  "#52c41a",
  "#722ed1",
  "#fa8c16",
  "#eb2f96",
  "#13c2c2",
  "#2f54eb",
  "#faad14",
  "#a0d911",
];

// Metrics for Pages chart
const PAGES_METRICS = ["pages_processed", "failed_pages"];

/**
 * Format a date string for display on chart axis.
 *
 * @param {string} dateStr - ISO date string
 * @return {string} Formatted date
 */
function formatDate(dateStr) {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/**
 * Format a number for display in tooltips.
 *
 * @param {number} value - Number to format
 * @return {string} Formatted number
 */
function formatValue(value) {
  if (value === null || value === undefined) {
    return "0";
  }
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toLocaleString();
}

/**
 * Format metric name for display.
 *
 * @param {string} metric - Metric name with underscores
 * @return {string} Human-readable metric name
 */
function formatMetricName(metric) {
  return metric.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
}

/**
 * Custom tooltip for the chart.
 *
 * @return {JSX.Element|null} The rendered tooltip or null.
 */
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="metrics-chart-tooltip">
      <p className="tooltip-label">{formatDate(label)}</p>
      {payload.map((entry, index) => (
        <p key={index} style={{ color: entry.color }}>
          {entry.name}: {formatValue(entry.value)}
        </p>
      ))}
    </div>
  );
}

CustomTooltip.propTypes = {
  active: PropTypes.bool,
  payload: PropTypes.array,
  label: PropTypes.string,
};

/**
 * Pages Processed chart - shows pages_processed and failed_pages.
 *
 * @return {JSX.Element} The rendered pages chart component.
 */
function PagesChart({ data, loading }) {
  // Process data for the line chart
  const chartData = useMemo(() => {
    if (!data?.daily_trend || data.daily_trend.length === 0) {
      return [];
    }

    return data.daily_trend.map((item) => ({
      date: item.date,
      pages_processed: item.metrics?.pages_processed || 0,
      failed_pages: item.metrics?.failed_pages || 0,
    }));
  }, [data]);

  if (loading) {
    return (
      <Card
        title="Pages Processed (Last 30 Days)"
        className="metrics-chart-card"
      >
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!chartData.length) {
    return (
      <Card
        title="Pages Processed (Last 30 Days)"
        className="metrics-chart-card"
      >
        <Empty description="No data available" />
      </Card>
    );
  }

  return (
    <Card
      title="Pages Processed (Last 30 Days)"
      className="metrics-chart-card chart-card"
    >
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#f0f0f0"
            />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              formatter={(value) => (
                <span style={{ color: "#262626" }}>{value}</span>
              )}
            />
            <Line
              type="monotone"
              dataKey="pages_processed"
              name="Pages Processed"
              stroke="#1890ff"
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
            <Line
              type="monotone"
              dataKey="failed_pages"
              name="Failed Pages"
              stroke="#ff4d4f"
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 2 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

PagesChart.propTypes = {
  data: PropTypes.shape({
    daily_trend: PropTypes.arrayOf(
      PropTypes.shape({
        date: PropTypes.string,
        metrics: PropTypes.object,
      }),
    ),
  }),
  loading: PropTypes.bool,
};

/**
 * Trend Analysis chart - shows other metrics (not pages).
 *
 * @return {JSX.Element} The rendered trend analysis chart component.
 */
function TrendAnalysisChart({ data, loading }) {
  // State for selected metrics
  const [selectedMetrics, setSelectedMetrics] = useState([
    "documents_processed",
  ]);

  // Process data and extract available metrics (excluding pages metrics)
  const { chartData, availableMetrics, metricOptions } = useMemo(() => {
    if (!data?.daily_trend || data.daily_trend.length === 0) {
      return { chartData: [], availableMetrics: [], metricOptions: [] };
    }

    // Collect all unique metric names, excluding pages metrics
    const metricNamesSet = new Set();
    data.daily_trend.forEach((item) => {
      if (item.metrics) {
        Object.keys(item.metrics).forEach((key) => {
          if (!PAGES_METRICS.includes(key)) {
            metricNamesSet.add(key);
          }
        });
      }
    });
    const metricNames = Array.from(metricNamesSet).sort((a, b) =>
      a.localeCompare(b),
    );

    const transformed = data.daily_trend.map((item) => ({
      date: item.date,
      ...item.metrics,
    }));

    const options = metricNames.map((metric) => ({
      label: formatMetricName(metric),
      value: metric,
    }));

    return {
      chartData: transformed,
      availableMetrics: metricNames,
      metricOptions: options,
    };
  }, [data]);

  // Filter to only show selected metrics that exist
  const metricsToShow = useMemo(() => {
    return selectedMetrics.filter((m) => availableMetrics.includes(m));
  }, [selectedMetrics, availableMetrics]);

  if (loading) {
    return (
      <Card
        title="Trend Analysis (Last 30 Days)"
        className="metrics-chart-card"
      >
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!chartData.length) {
    return (
      <Card
        title="Trend Analysis (Last 30 Days)"
        className="metrics-chart-card"
      >
        <Empty description="No data available" />
      </Card>
    );
  }

  // Filter dropdown menu items
  const filterMenuItems = metricOptions.map((opt) => ({
    key: opt.value,
    label: opt.label,
  }));

  const handleFilterClick = ({ key }) => {
    if (selectedMetrics.includes(key)) {
      setSelectedMetrics(selectedMetrics.filter((m) => m !== key));
    } else {
      setSelectedMetrics([...selectedMetrics, key]);
    }
  };

  // Card extra content with filter dropdown
  const cardExtra =
    availableMetrics.length > 1 ? (
      <Dropdown
        menu={{
          items: filterMenuItems,
          onClick: handleFilterClick,
          selectable: true,
          multiple: true,
          selectedKeys: selectedMetrics,
        }}
        trigger={["click"]}
      >
        <Button icon={<FilterOutlined />} size="small">
          Filter
        </Button>
      </Dropdown>
    ) : null;

  // Colors for trend metrics
  const TREND_BAR_COLORS = {
    documents_processed: "#faad14",
    llm_calls: "#722ed1",
    prompt_executions: "#52c41a",
    deployed_api_requests: "#13c2c2",
    llm_usage: "#eb2f96",
    etl_pipeline_executions: "#fa8c16",
    challenges: "#2f54eb",
    summarization_calls: "#a0d911",
  };

  const getTrendColor = (metric, idx) =>
    TREND_BAR_COLORS[metric] || TREND_COLORS[idx % TREND_COLORS.length];

  return (
    <Card
      title="Trend Analysis (Last 30 Days)"
      extra={cardExtra}
      className="metrics-chart-card chart-card"
    >
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#f0f0f0"
            />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            {metricsToShow.length > 1 && (
              <Legend
                formatter={(value) => (
                  <span style={{ color: "#262626" }}>{value}</span>
                )}
              />
            )}
            {metricsToShow.map((metric, idx) => (
              <Line
                key={metric}
                type="monotone"
                dataKey={metric}
                name={formatMetricName(metric)}
                stroke={getTrendColor(metric, idx)}
                strokeWidth={2}
                dot={{ r: 3, strokeWidth: 2 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

TrendAnalysisChart.propTypes = {
  data: PropTypes.shape({
    daily_trend: PropTypes.arrayOf(
      PropTypes.shape({
        date: PropTypes.string,
        metrics: PropTypes.object,
      }),
    ),
  }),
  loading: PropTypes.bool,
};

// HITL bar colors (blue + yellow/gold)
const HITL_COLORS = {
  hitl_reviews: "#69b1ff",
  hitl_completions: "#faad14",
};

/**
 * HITL Reviews & Completions chart.
 * Returns null when no HITL data is available (e.g. on OSS).
 *
 * @return {JSX.Element|null} The rendered HITL chart or null.
 */
function HITLChart({ data, loading }) {
  const chartData = useMemo(() => {
    if (!data?.daily_trend || data.daily_trend.length === 0) {
      return [];
    }

    return data.daily_trend
      .filter(
        (item) =>
          item.metrics?.hitl_reviews > 0 || item.metrics?.hitl_completions > 0,
      )
      .map((item) => ({
        date: item.date,
        hitl_reviews: item.metrics?.hitl_reviews || 0,
        hitl_completions: item.metrics?.hitl_completions || 0,
      }));
  }, [data]);

  if (loading) {
    return (
      <Card
        title="HITL Reviews & Completions (Last 30 Days)"
        className="metrics-chart-card"
      >
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  // No HITL data — return null so the component doesn't render on OSS
  if (!chartData.length) {
    return null;
  }

  return (
    <Card
      title="HITL Reviews & Completions (Last 30 Days)"
      className="metrics-chart-card chart-card"
    >
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#f0f0f0"
            />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 12 }}
              stroke="#8c8c8c"
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              formatter={(value) => (
                <span style={{ color: "#262626" }}>
                  {formatMetricName(value)}
                </span>
              )}
            />
            <Bar
              dataKey="hitl_reviews"
              name="hitl_reviews"
              fill={HITL_COLORS.hitl_reviews}
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="hitl_completions"
              name="hitl_completions"
              fill={HITL_COLORS.hitl_completions}
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

HITLChart.propTypes = {
  data: PropTypes.shape({
    daily_trend: PropTypes.arrayOf(
      PropTypes.shape({
        date: PropTypes.string,
        metrics: PropTypes.object,
      }),
    ),
  }),
  loading: PropTypes.bool,
};

export { PagesChart, TrendAnalysisChart, HITLChart };
