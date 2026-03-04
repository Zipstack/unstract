import {
  BarChartOutlined,
  CreditCardOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  RocketOutlined,
  SlackOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Col,
  DatePicker,
  Row,
  Space,
  Tabs,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { EmptyPlaceholder } from "../../assets";
import { evictExpiredCache } from "../../helpers/metricsCache";
import {
  useMetricsOverview,
  useRecentActivity,
  useSubscriptionUsage,
} from "../../hooks/useMetricsData";
import { useSessionStore } from "../../store/session-store";
import { DeploymentUsageTable } from "./LLMUsageTable";
import { HITLChart, PagesChart, TrendAnalysisChart } from "./MetricsChart";
import { MetricsSummary } from "./MetricsSummary";
import { RecentActivity } from "./RecentActivity";

import "./MetricsDashboard.css";

// Cloud-only: Plan banner with subscription details
let PlanBanner;
try {
  const mod = await import(
    "../../plugins/unstract-subscription/components/PlanBanner.jsx"
  );
  PlanBanner = mod.PlanBanner;
} catch {
  // Plugin unavailable - no banner on OSS
}

// Cloud-only: Subscription usage tab
let SubscriptionUsageTab;
try {
  const mod = await import(
    "../../plugins/unstract-subscription/components/SubscriptionUsageTab.jsx"
  );
  SubscriptionUsageTab = mod.SubscriptionUsageTab;
} catch {
  // Plugin unavailable - no subscription tab on OSS
}

const { Title } = Typography;
const { RangePicker } = DatePicker;

function MetricsDashboard() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const orgName = sessionDetails?.orgName;

  // Evict expired cache entries on mount
  useEffect(() => {
    evictExpiredCache();
  }, []);

  // Stabilise "now" to start-of-minute so remounts within the same
  // minute produce identical ISO strings → same cache keys → cache hits.
  const [stableNow] = useState(() => dayjs().startOf("minute"));

  // Date range state (default: last 30 days)
  const [dateRange, setDateRange] = useState(() => [
    stableNow.subtract(30, "day"),
    stableNow,
  ]);

  // Fixed 30-day range for activity charts (independent of date picker)
  const chartStart = useMemo(
    () => stableNow.subtract(30, "day").toISOString(),
    [stableNow],
  );
  const chartEnd = useMemo(() => stableNow.toISOString(), [stableNow]);

  // API hooks - pass date range to overview (for summary cards)
  const {
    data: overviewData,
    loading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useMetricsOverview(
    dateRange[0]?.toISOString(),
    dateRange[1]?.toISOString(),
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

  // Subscription usage (cloud-only, returns null on OSS)
  const {
    data: subscriptionData,
    loading: subscriptionLoading,
    refetch: refetchSubscription,
  } = useSubscriptionUsage();

  // Active tab (controls date picker visibility)
  const [activeTab, setActiveTab] = useState("overview");

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
    refetchSubscription();
  }, [refetchOverview, refetchChart, refetchActivity, refetchSubscription]);

  // Check if all data sources are empty (no activity at all)
  const isDataLoading = overviewLoading || chartLoading || activityLoading;
  const hasNoData = useMemo(() => {
    if (isDataLoading) {
      return false;
    }
    const hasOverview =
      overviewData?.totals?.some((m) => m.total_value > 0) || false;
    const hasChart = chartData?.daily_trend?.length > 0 || false;
    const hasActivity = activityData?.activity?.length > 0 || false;
    return !hasOverview && !hasChart && !hasActivity;
  }, [isDataLoading, overviewData, chartData, activityData]);

  const tabItems = [
    {
      key: "overview",
      label: (
        <span>
          <DashboardOutlined /> Overview
        </span>
      ),
      children: hasNoData ? (
        <div className="metrics-empty-state">
          <EmptyPlaceholder className="metrics-empty-state-icon" />
          <Typography.Title level={4} className="metrics-empty-state-title">
            No activity yet
          </Typography.Title>
          <Typography.Text
            type="secondary"
            className="metrics-empty-state-text"
          >
            Run a workflow or API deployment to see your metrics here.
          </Typography.Text>
          <Space className="metrics-empty-state-actions">
            <Button
              type="primary"
              icon={<RocketOutlined />}
              onClick={() => navigate(`/${orgName}/workflows`)}
            >
              Create Workflow
            </Button>
            <Button onClick={() => navigate(`/${orgName}/tools`)}>
              Open Prompt Studio
            </Button>
          </Space>
        </div>
      ) : (
        <>
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
            <Col xs={24} lg={12}>
              <HITLChart data={chartData} loading={chartLoading} />
            </Col>
            <Col xs={24} lg={12}>
              <TrendAnalysisChart data={chartData} loading={chartLoading} />
            </Col>
          </Row>
        </>
      ),
    },
    {
      key: "llm-usage",
      label: (
        <span>
          <ThunderboltOutlined /> Usage by Deployment
        </span>
      ),
      children: (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <DeploymentUsageTable
              startDate={dateRange[0]?.toISOString()}
              endDate={dateRange[1]?.toISOString()}
            />
          </Col>
        </Row>
      ),
    },
  ];

  // Cloud-only: add subscription usage tab
  if (SubscriptionUsageTab) {
    tabItems.push({
      key: "subscription",
      label: (
        <span>
          <CreditCardOutlined /> Subscription
        </span>
      ),
      children: (
        <SubscriptionUsageTab
          data={subscriptionData}
          loading={subscriptionLoading}
          overviewData={overviewData}
          overviewLoading={overviewLoading}
        />
      ),
    });
  }

  return (
    <div className="metrics-dashboard">
      <div className="metrics-topbar">
        <div className="metrics-topbar-left">
          <BarChartOutlined className="metrics-topbar-icon" />
          <Title level={4} style={{ margin: 0 }}>
            Dashboard
          </Title>
        </div>

        <Space className="metrics-topbar-right">
          <Button
            icon={<FileSearchOutlined />}
            type="link"
            onClick={() =>
              window.open(
                "https://docs.unstract.com/unstract/index.html",
                "_blank",
                "noopener,noreferrer",
              )
            }
            className="metrics-header-button"
          >
            Documentation
          </Button>
          <Button
            icon={<SlackOutlined />}
            type="link"
            onClick={() =>
              window.open(
                "https://join-slack.unstract.com/",
                "_blank",
                "noopener,noreferrer",
              )
            }
            className="metrics-header-button"
          >
            Slack Community
          </Button>
        </Space>
      </div>

      {PlanBanner && subscriptionData && <PlanBanner />}

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

      <Tabs
        items={tabItems}
        activeKey={activeTab}
        onChange={setActiveTab}
        tabBarExtraContent={
          <Space>
            {activeTab !== "subscription" && (
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
                  // 90-day preset only for overview (deployment usage capped at 30 days)
                  ...(activeTab !== "llm-usage"
                    ? [
                        {
                          label: "Last 90 Days",
                          value: [dayjs().subtract(90, "day"), dayjs()],
                        },
                      ]
                    : []),
                ]}
              />
            )}
            <Button icon={<ReloadOutlined />} onClick={handleRefresh} />
          </Space>
        }
      />
    </div>
  );
}

export { MetricsDashboard };
