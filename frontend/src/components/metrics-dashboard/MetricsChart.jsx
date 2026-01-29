import { Card, Empty, Spin, Button, Dropdown, Progress } from "antd";
import { FilterOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
} from "recharts";

import "./MetricsDashboard.css";

// Colors for charts and progress bars
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
  if (value === null || value === undefined) return "0";
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toLocaleString();
}

/**
 * Custom tooltip for the chart.
 *
 * @return {JSX.Element|null} The rendered tooltip or null.
 */
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

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

// Metrics for Pages chart (left chart)
const PAGES_METRICS = ["pages_processed", "failed_pages"];

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
 * Line chart component for displaying time series data.
 * Supports multiple metrics as separate lines with multi-select.
 *
 * @return {JSX.Element} The rendered chart component.
 */
function MetricsChart({ data, loading, title = "Daily Activity" }) {
  // State for selected metrics
  const [selectedMetrics, setSelectedMetrics] = useState([
    "pages_processed",
    "documents_processed",
  ]);

  // Process data and extract available metrics
  const { chartData, availableMetrics } = useMemo(() => {
    if (!data?.daily_trend || data.daily_trend.length === 0) {
      return { chartData: [], availableMetrics: [] };
    }

    const firstItem = data.daily_trend[0];

    // New format: { date, metrics: { metric1: val, metric2: val } }
    if (firstItem && typeof firstItem === "object" && firstItem.metrics) {
      // Collect ALL unique metric names from ALL days (not just first day)
      const metricNamesSet = new Set();
      data.daily_trend.forEach((item) => {
        if (item.metrics) {
          Object.keys(item.metrics).forEach((key) => metricNamesSet.add(key));
        }
      });
      const metricNames = Array.from(metricNamesSet).sort();

      const transformed = data.daily_trend.map((item) => ({
        date: item.date,
        displayDate: formatDate(item.date),
        ...item.metrics,
      }));
      return { chartData: transformed, availableMetrics: metricNames };
    }

    // Legacy format: { date, value, count }
    const transformed = data.daily_trend.map((item) => ({
      date: item.date,
      displayDate: formatDate(item.date),
      value: item.value || 0,
      count: item.count || 0,
    }));
    return { chartData: transformed, availableMetrics: ["value"] };
  }, [data]);

  // Filter to only show selected metrics that exist in data
  const metricsToShow = useMemo(() => {
    return selectedMetrics.filter((m) => availableMetrics.includes(m));
  }, [selectedMetrics, availableMetrics]);

  // Build options for the Select dropdown
  const metricOptions = useMemo(() => {
    return availableMetrics.map((metric) => ({
      label: formatMetricName(metric),
      value: metric,
    }));
  }, [availableMetrics]);

  if (loading) {
    return (
      <Card title={title} className="metrics-chart-card">
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!chartData.length) {
    return (
      <Card title={title} className="metrics-chart-card">
        <Empty description="No trend data available" />
      </Card>
    );
  }

  // Bar colors - metric-specific for key metrics, fallback array for others
  const METRIC_BAR_COLORS = {
    pages_processed: "#1890ff",
    documents_processed: "#52c41a",
    failed_pages: "#ff4d4f", // Red for failures
    llm_calls: "#722ed1",
    prompt_executions: "#faad14",
    llm_usage: "#13c2c2",
  };
  const DEFAULT_BAR_COLORS = [
    "#1890ff",
    "#faad14",
    "#52c41a",
    "#722ed1",
    "#13c2c2",
  ];
  const getBarColor = (metric, idx) =>
    METRIC_BAR_COLORS[metric] ||
    DEFAULT_BAR_COLORS[idx % DEFAULT_BAR_COLORS.length];

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

  return (
    <Card
      title={title}
      extra={cardExtra}
      className="metrics-chart-card chart-card"
    >
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={chartData}
            margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
            barCategoryGap="15%"
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
              <Bar
                key={metric}
                dataKey={metric}
                name={formatMetricName(metric)}
                fill={getBarColor(metric, idx)}
                radius={[4, 4, 0, 0]}
                maxBarSize={80}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

/**
 * Multi-series line chart for comparing different metrics over time.
 * Each metric is rendered as a separate line with its own color.
 *
 * @return {JSX.Element} The rendered multi-series chart component.
 */
function MultiSeriesChart({ data, loading, title = "Metrics Over Time" }) {
  const { chartData, metricNames } = useMemo(() => {
    if (!data?.series) return { chartData: [], metricNames: [] };

    // Transform series data: { metric_name: [{ date, value }] }
    // into chart format: [{ date, metric1: val, metric2: val }]
    const dateMap = new Map();
    const names = [];

    Object.entries(data.series).forEach(([metricName, values]) => {
      names.push(metricName);
      values.forEach(({ date, value }) => {
        if (!dateMap.has(date)) {
          dateMap.set(date, { date });
        }
        dateMap.get(date)[metricName] = value;
      });
    });

    // Sort by date
    const sorted = Array.from(dateMap.values()).sort(
      (a, b) => new Date(a.date) - new Date(b.date)
    );

    return { chartData: sorted, metricNames: names };
  }, [data]);

  if (loading) {
    return (
      <Card title={title} className="metrics-chart-card">
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!chartData.length || !metricNames.length) {
    return (
      <Card title={title} className="metrics-chart-card">
        <Empty description="No series data available" />
      </Card>
    );
  }

  return (
    <Card title={title} className="metrics-chart-card">
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={320}>
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
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
              width={60}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: 10 }}
              formatter={(value) => (
                <span style={{ color: "#262626" }}>
                  {value
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (l) => l.toUpperCase())}
                </span>
              )}
            />
            {metricNames.map((metric, idx) => (
              <Line
                key={metric}
                type="monotone"
                dataKey={metric}
                name={metric}
                stroke={TREND_COLORS[idx % TREND_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 2, strokeWidth: 2 }}
                activeDot={{ r: 5 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

/**
 * Trend Analysis chart showing line trends for metrics over time.
 * Displays the same data as the bar chart but as lines to show trends.
 *
 * @return {JSX.Element} The rendered trend chart component.
 */
function MetricsBreakdown({ data, loading }) {
  // State for selected metrics (show pages and documents by default)
  const [selectedMetrics, setSelectedMetrics] = useState([
    "pages_processed",
    "documents_processed",
  ]);

  // Process data for the line chart
  const { chartData, availableMetrics, metricOptions } = useMemo(() => {
    if (!data?.daily_trend || data.daily_trend.length === 0) {
      return { chartData: [], availableMetrics: [], metricOptions: [] };
    }

    // Collect all unique metric names
    const metricNamesSet = new Set();
    data.daily_trend.forEach((item) => {
      if (item.metrics) {
        Object.keys(item.metrics).forEach((key) => metricNamesSet.add(key));
      }
    });
    const metricNames = Array.from(metricNamesSet).sort();

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
        <Empty description="No trend data available" />
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
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
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
                stroke={TREND_COLORS[idx % TREND_COLORS.length]}
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

/**
 * Pages Processed chart - shows pages_processed and failed_pages.
 * Matches the reference design's left chart.
 *
 * @return {JSX.Element} The rendered pages chart component.
 */
function PagesChart({ data, loading }) {
  // Process data for the bar chart
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
      })
    ),
  }),
  loading: PropTypes.bool,
};

/**
 * Trend Analysis chart - shows other metrics (not pages).
 * Matches the reference design's right chart.
 *
 * @return {JSX.Element} The rendered trend analysis chart component.
 */
function TrendAnalysisChart({ data, loading }) {
  // State for selected metrics
  const [selectedMetrics, setSelectedMetrics] = useState([
    "documents_processed",
    "llm_calls",
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
    const metricNames = Array.from(metricNamesSet).sort();

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
      })
    ),
  }),
  loading: PropTypes.bool,
};

MetricsChart.propTypes = {
  data: PropTypes.shape({
    daily_trend: PropTypes.arrayOf(
      PropTypes.shape({
        date: PropTypes.string,
        value: PropTypes.number,
        count: PropTypes.number,
        metrics: PropTypes.object,
      })
    ),
  }),
  loading: PropTypes.bool,
  title: PropTypes.string,
};

MultiSeriesChart.propTypes = {
  data: PropTypes.shape({
    series: PropTypes.objectOf(
      PropTypes.arrayOf(
        PropTypes.shape({
          date: PropTypes.string,
          value: PropTypes.number,
        })
      )
    ),
  }),
  loading: PropTypes.bool,
  title: PropTypes.string,
};

MetricsBreakdown.propTypes = {
  data: PropTypes.shape({
    daily_trend: PropTypes.arrayOf(
      PropTypes.shape({
        date: PropTypes.string,
        metrics: PropTypes.object,
      })
    ),
  }),
  loading: PropTypes.bool,
};

// Priority order for metrics comparison display
const COMPARISON_PRIORITY = [
  "pages_processed",
  "documents_processed",
  "failed_pages",
  "llm_calls",
  "prompt_executions",
  "deployed_api_requests",
  "llm_usage",
  "etl_pipeline_executions",
];

// Colors for progress bars - all blue for consistent UI, red for failed
const METRIC_COLORS = {
  pages_processed: "#1890ff",
  documents_processed: "#1890ff",
  failed_pages: "#ff4d4f",
  llm_calls: "#1890ff",
  prompt_executions: "#1890ff",
  deployed_api_requests: "#1890ff",
  llm_usage: "#1890ff",
  etl_pipeline_executions: "#1890ff",
  challenges: "#1890ff",
  summarization_calls: "#1890ff",
};

/**
 * Usage quota style component showing metrics with progress bars.
 * Matches the reference design's "Usage Quota" section.
 *
 * @return {JSX.Element} The rendered usage quota component.
 */
function MetricsComparison({ data, loading }) {
  // Process summary data for progress bars
  const metricsData = useMemo(() => {
    if (!data?.summary || data.summary.length === 0) {
      return [];
    }

    // Sort by priority order
    const sorted = [...data.summary].sort((a, b) => {
      const aIndex = COMPARISON_PRIORITY.indexOf(a.metric_name);
      const bIndex = COMPARISON_PRIORITY.indexOf(b.metric_name);
      if (aIndex === -1 && bIndex === -1) return 0;
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });

    // Find max value for percentage calculation
    const max = Math.max(...sorted.map((m) => m.total_value || 0), 1);

    return sorted.map((item) => ({
      ...item,
      displayName: formatMetricName(item.metric_name),
      percent: Math.round(((item.total_value || 0) / max) * 100),
      color: METRIC_COLORS[item.metric_name] || "#1890ff",
    }));
  }, [data]);

  if (loading) {
    return (
      <Card title="Usage Summary" className="metrics-chart-card">
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!metricsData.length) {
    return (
      <Card title="Usage Summary" className="metrics-chart-card">
        <Empty description="No usage data available" />
      </Card>
    );
  }

  return (
    <Card title="Usage Summary" className="metrics-chart-card chart-card">
      <div className="usage-quota-list">
        {metricsData.map((metric) => (
          <div key={metric.metric_name} className="usage-quota-item">
            <div className="usage-quota-header">
              <span className="usage-quota-label">{metric.displayName}</span>
              <span className="usage-quota-value">
                {formatValue(metric.total_value || 0)}
              </span>
            </div>
            <Progress
              percent={metric.percent}
              showInfo={false}
              strokeColor={metric.color}
              trailColor="#f0f0f0"
              size="small"
            />
          </div>
        ))}
      </div>
    </Card>
  );
}

MetricsComparison.propTypes = {
  data: PropTypes.shape({
    summary: PropTypes.arrayOf(
      PropTypes.shape({
        metric_name: PropTypes.string.isRequired,
        total_value: PropTypes.number,
        total_count: PropTypes.number,
        average_value: PropTypes.number,
      })
    ),
  }),
  loading: PropTypes.bool,
};

export {
  MetricsChart,
  MetricsBreakdown,
  MultiSeriesChart,
  MetricsComparison,
  PagesChart,
  TrendAnalysisChart,
};
