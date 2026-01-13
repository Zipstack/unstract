import { useState, useCallback, useMemo } from "react";
import {
  Typography,
  DatePicker,
  Card,
  Row,
  Col,
  Button,
  Space,
  Alert,
  Tabs,
  Radio,
  Tag,
  Tooltip,
} from "antd";
import {
  ReloadOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  CalendarOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";

import {
  useMetricsOverview,
  useMetricsSummary,
} from "../../hooks/useMetricsData";
import { MetricsSummary } from "./MetricsSummary";
import { MetricsTable } from "./MetricsTable";
import { MetricsChart, MetricsBreakdown } from "./MetricsChart";

import "./MetricsDashboard.css";

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// Source options for data granularity
const SOURCE_OPTIONS = [
  { label: "Auto", value: "auto" },
  { label: "Hourly", value: "hourly" },
  { label: "Daily", value: "daily" },
  { label: "Monthly", value: "monthly" },
];

// Helper to get recommended source based on date range
const getRecommendedSource = (startDate, endDate) => {
  if (!startDate || !endDate) return "auto";
  const days = endDate.diff(startDate, "day");
  if (days <= 7) return "hourly";
  if (days <= 90) return "daily";
  return "monthly";
};

function MetricsDashboard() {
  // Date range state (default: last 30 days)
  const [dateRange, setDateRange] = useState([
    dayjs().subtract(30, "day"),
    dayjs(),
  ]);
  // Track active tab to lazy load summary data
  const [activeTab, setActiveTab] = useState("overview");
  // Data source for detailed view
  const [dataSource, setDataSource] = useState("auto");

  // Calculate recommended source based on date range
  const recommendedSource = useMemo(
    () => getRecommendedSource(dateRange[0], dateRange[1]),
    [dateRange]
  );

  // API hooks - pass date range to overview
  const {
    data: overviewData,
    loading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useMetricsOverview(
    dateRange[0]?.toISOString(),
    dateRange[1]?.toISOString()
  );

  // Only fetch summary data when on "details" tab
  const shouldFetchSummary = activeTab === "details";
  const {
    data: summaryData,
    loading: summaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useMetricsSummary(
    shouldFetchSummary ? dateRange[0]?.toISOString() : null,
    shouldFetchSummary ? dateRange[1]?.toISOString() : null,
    null, // metricName
    dataSource
  );

  // Handle date range change
  const handleDateChange = useCallback((dates) => {
    if (dates && dates.length === 2) {
      setDateRange(dates);
    }
  }, []);

  // Handle tab change
  const handleTabChange = useCallback((key) => {
    setActiveTab(key);
  }, []);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    refetchOverview();
    if (activeTab === "details") {
      refetchSummary();
    }
  }, [refetchOverview, refetchSummary, activeTab]);

  // Handle source change
  const handleSourceChange = useCallback((e) => {
    setDataSource(e.target.value);
  }, []);

  // Get the actual source being used (for display)
  const actualSource = summaryData?.source || dataSource;

  const tabItems = [
    {
      key: "overview",
      label: "Overview",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <MetricsSummary data={overviewData} loading={overviewLoading} />
          </Col>
          <Col xs={24} lg={12}>
            <MetricsChart
              data={overviewData}
              loading={overviewLoading}
              title="Last 7 Days Activity"
            />
          </Col>
          <Col xs={24} lg={12}>
            <MetricsBreakdown data={overviewData} loading={overviewLoading} />
          </Col>
        </Row>
      ),
    },
    {
      key: "details",
      label: "Detailed View",
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card
              title={
                <Space>
                  <span>Metrics Summary</span>
                  {actualSource && actualSource !== "auto" && (
                    <Tooltip
                      title={`Data from ${actualSource} aggregated table`}
                    >
                      <Tag
                        icon={<CalendarOutlined />}
                        color={
                          actualSource === "hourly"
                            ? "blue"
                            : actualSource === "daily"
                            ? "green"
                            : "purple"
                        }
                      >
                        {actualSource}
                      </Tag>
                    </Tooltip>
                  )}
                </Space>
              }
              extra={
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Data source:
                  </Text>
                  <Radio.Group
                    options={SOURCE_OPTIONS}
                    onChange={handleSourceChange}
                    value={dataSource}
                    optionType="button"
                    buttonStyle="solid"
                    size="small"
                  />
                  {dataSource === "auto" && (
                    <Tooltip
                      title={`Auto-selected: ${recommendedSource} (based on ${dateRange[1]?.diff(
                        dateRange[0],
                        "day"
                      )} day range)`}
                    >
                      <Tag icon={<ClockCircleOutlined />} color="default">
                        {recommendedSource}
                      </Tag>
                    </Tooltip>
                  )}
                </Space>
              }
            >
              <MetricsTable data={summaryData} loading={summaryLoading} />
            </Card>
          </Col>
        </Row>
      ),
    },
  ];

  return (
    <div className="metrics-dashboard">
      <div className="metrics-header">
        <div className="metrics-title-section">
          <Title level={3}>
            <BarChartOutlined /> Metrics Dashboard
          </Title>
          <Text type="secondary">
            Monitor your document processing and API usage metrics
          </Text>
        </div>

        <Space className="metrics-controls">
          <RangePicker
            value={dateRange}
            onChange={handleDateChange}
            disabledDate={(current) => current && current > dayjs()}
            allowClear={false}
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
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            Refresh
          </Button>
        </Space>
      </div>

      {overviewError && (
        <Alert
          message="Error loading overview"
          description={overviewError}
          type="error"
          showIcon
          closable
          className="metrics-error"
        />
      )}

      {summaryError && activeTab === "details" && (
        <Alert
          message="Error loading detailed metrics"
          description={summaryError}
          type="error"
          showIcon
          closable
          className="metrics-error"
        />
      )}

      <Tabs
        defaultActiveKey="overview"
        activeKey={activeTab}
        onChange={handleTabChange}
        items={tabItems}
      />
    </div>
  );
}

export { MetricsDashboard };
