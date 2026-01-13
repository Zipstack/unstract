import {
  Card,
  Progress,
  Typography,
  Row,
  Col,
  Empty,
  Spin,
  Select,
} from "antd";
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
  AreaChart,
  Area,
} from "recharts";

import "./MetricsDashboard.css";

const { Text } = Typography;

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

// Default metrics to show initially
const DEFAULT_SELECTED_METRICS = [
  "documents_processed",
  "pages_processed",
  "llm_calls",
];

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
function MetricsChart({
  data,
  loading,
  title = "Daily Activity",
  showArea = false,
}) {
  // State for selected metrics
  const [selectedMetrics, setSelectedMetrics] = useState(
    DEFAULT_SELECTED_METRICS
  );

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

  const ChartComponent = showArea ? AreaChart : LineChart;
  const DataComponent = showArea ? Area : Line;

  return (
    <Card title={title} className="metrics-chart-card">
      {availableMetrics.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <Select
            mode="multiple"
            placeholder="Select metrics to display"
            value={selectedMetrics}
            onChange={setSelectedMetrics}
            options={metricOptions}
            style={{ width: "100%" }}
            maxTagCount="responsive"
            allowClear
          />
        </div>
      )}
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={280}>
          <ChartComponent
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
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            {metricsToShow.length > 1 && <Legend />}
            {metricsToShow.map((metric, idx) => (
              <DataComponent
                key={metric}
                type="monotone"
                dataKey={metric}
                name={formatMetricName(metric)}
                stroke={TREND_COLORS[idx % TREND_COLORS.length]}
                fill={
                  showArea ? TREND_COLORS[idx % TREND_COLORS.length] : undefined
                }
                fillOpacity={showArea ? 0.3 : undefined}
                strokeWidth={2}
                dot={{ r: 3, strokeWidth: 2 }}
                activeDot={{ r: 5 }}
              />
            ))}
          </ChartComponent>
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
              formatter={(value) =>
                value
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (l) => l.toUpperCase())
              }
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
 * Metric breakdown component showing distribution of metrics.
 *
 * @return {JSX.Element} The rendered breakdown component.
 */
function MetricsBreakdown({ data, loading }) {
  const breakdown = useMemo(() => {
    if (!data?.totals) return [];

    const total = data.totals.reduce((sum, m) => sum + (m.total_value || 0), 0);
    if (total === 0) return [];

    return data.totals.map((metric, index) => ({
      ...metric,
      percentage: Math.round(((metric.total_value || 0) / total) * 100),
      color: TREND_COLORS[index % TREND_COLORS.length],
      displayName: metric.metric_name
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase()),
    }));
  }, [data]);

  if (loading) {
    return (
      <Card title="Metrics Distribution" className="metrics-chart-card">
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!breakdown.length) {
    return (
      <Card title="Metrics Distribution" className="metrics-chart-card">
        <Empty description="No data available" />
      </Card>
    );
  }

  return (
    <Card title="Metrics Distribution" className="metrics-chart-card">
      <div className="breakdown-chart">
        {breakdown.map((metric) => (
          <div key={metric.metric_name} className="breakdown-item">
            <Row justify="space-between" align="middle">
              <Col>
                <Text>{metric.displayName}</Text>
              </Col>
              <Col>
                <Text strong>{metric.percentage}%</Text>
              </Col>
            </Row>
            <Progress
              percent={metric.percentage}
              showInfo={false}
              strokeColor={metric.color}
              size="small"
            />
          </div>
        ))}
      </div>
    </Card>
  );
}

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
  showArea: PropTypes.bool,
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
    totals: PropTypes.arrayOf(
      PropTypes.shape({
        metric_name: PropTypes.string.isRequired,
        total_value: PropTypes.number,
      })
    ),
  }),
  loading: PropTypes.bool,
};

export { MetricsChart, MetricsBreakdown, MultiSeriesChart };
