import { useState, useCallback, useMemo } from "react";
import { Typography, DatePicker, Row, Col, Button, Space, Alert } from "antd";
import { ReloadOutlined, BarChartOutlined } from "@ant-design/icons";
import dayjs from "dayjs";

import {
  useMetricsOverview,
  useRecentActivity,
} from "../../hooks/useMetricsData";
import { MetricsSummary } from "./MetricsSummary";
import { PagesChart, TrendAnalysisChart } from "./MetricsChart";
import { RecentActivity } from "./RecentActivity";

import "./MetricsDashboard.css";

const { Title } = Typography;
const { RangePicker } = DatePicker;

function MetricsDashboard() {
  // Date range state (default: last 30 days)
  const [dateRange, setDateRange] = useState([
    dayjs().subtract(30, "day"),
    dayjs(),
  ]);

  // Fixed 30-day range for activity charts (independent of date picker)
  const chartStart = useMemo(
    () => dayjs().subtract(30, "day").toISOString(),
    []
  );
  const chartEnd = useMemo(() => dayjs().toISOString(), []);

  // API hooks - pass date range to overview (for summary cards)
  const {
    data: overviewData,
    loading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useMetricsOverview(
    dateRange[0]?.toISOString(),
    dateRange[1]?.toISOString()
  );

  // Fixed 30-day data for charts
  const {
    data: chartData,
    loading: chartLoading,
    refetch: refetchChart,
  } = useMetricsOverview(chartStart, chartEnd);

  // Recent activity (real-time, no date filter)
  const {
    data: activityData,
    loading: activityLoading,
    refetch: refetchActivity,
  } = useRecentActivity(5);

  // Handle date range change
  const handleDateChange = useCallback((dates) => {
    if (dates && dates.length === 2) {
      setDateRange(dates);
    }
  }, []);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    refetchOverview();
    refetchChart();
    refetchActivity();
  }, [refetchOverview, refetchChart, refetchActivity]);

  return (
    <div className="metrics-dashboard">
      <div className="metrics-topbar">
        <div className="metrics-topbar-left">
          <BarChartOutlined className="metrics-topbar-icon" />
          <Title level={4} style={{ margin: 0 }}>
            Metrics Dashboard
          </Title>
        </div>

        <Space className="metrics-topbar-right">
          <RangePicker
            value={dateRange}
            onChange={handleDateChange}
            disabledDate={(current) => current && current > dayjs()}
            allowClear={false}
            size="middle"
            presets={[
              {
                label: "Last 7 Days",
                value: [dayjs().subtract(7, "day"), dayjs()],
              },
              {
                label: "Last 30 Days",
                value: [dayjs().subtract(30, "day"), dayjs()],
              },
              {
                label: "Last 90 Days",
                value: [dayjs().subtract(90, "day"), dayjs()],
              },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={handleRefresh} />
        </Space>
      </div>

      {overviewError && (
        <Alert
          message="Error loading metrics"
          description={overviewError}
          type="error"
          showIcon
          closable
          className="metrics-error"
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24}>
          <MetricsSummary data={overviewData} loading={overviewLoading} />
        </Col>
        <Col xs={24} lg={16}>
          <PagesChart data={chartData} loading={chartLoading} />
        </Col>
        <Col xs={24} lg={8}>
          <RecentActivity data={activityData} loading={activityLoading} />
        </Col>
        <Col xs={24} lg={16}>
          <TrendAnalysisChart data={chartData} loading={chartLoading} />
        </Col>
      </Row>
    </div>
  );
}

export { MetricsDashboard };
