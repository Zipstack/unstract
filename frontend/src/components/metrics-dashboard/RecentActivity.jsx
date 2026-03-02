import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  PlayCircleOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { Card, Empty, List, Spin, Tag, Tooltip, Typography } from "antd";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import PropTypes from "prop-types";

import "./MetricsDashboard.css";

dayjs.extend(relativeTime);

const { Text } = Typography;

// Status configuration with colors and icons
const STATUS_CONFIG = {
  COMPLETED: {
    color: "success",
    icon: <CheckCircleOutlined />,
    label: "Completed",
  },
  RUNNING: {
    color: "processing",
    icon: <SyncOutlined spin />,
    label: "Processing",
  },
  QUEUED: {
    color: "default",
    icon: <ClockCircleOutlined />,
    label: "Queued",
  },
  ERROR: {
    color: "error",
    icon: <CloseCircleOutlined />,
    label: "Failed",
  },
};

// Execution type configuration
const TYPE_CONFIG = {
  etl: {
    label: "ETL Pipeline",
    icon: <BranchesOutlined />,
    color: "#722ed1",
  },
  api: {
    label: "API Request",
    icon: <ApiOutlined />,
    color: "#1890ff",
  },
  workflow: {
    label: "Workflow",
    icon: <PlayCircleOutlined />,
    color: "#52c41a",
  },
};

/**
 * Recent Activity component showing latest processing events.
 * Displays file executions categorized by type (ETL, API, Workflow).
 *
 * @return {JSX.Element} The rendered recent activity component.
 */
function RecentActivity({ data, loading }) {
  if (loading) {
    return (
      <Card title="Recent Activity" className="metrics-chart-card">
        <div className="metrics-loading">
          <Spin />
        </div>
      </Card>
    );
  }

  if (!data?.activity?.length) {
    return (
      <Card title="Recent Activity" className="metrics-chart-card">
        <Empty description="No recent activity" />
      </Card>
    );
  }

  return (
    <Card title="Recent Activity" className="metrics-chart-card chart-card">
      <List
        className="recent-activity-list"
        dataSource={data.activity}
        size="small"
        split={false}
        renderItem={(item) => {
          const statusConfig =
            STATUS_CONFIG[item.status] || STATUS_CONFIG.QUEUED;
          const typeConfig = TYPE_CONFIG[item.type] || TYPE_CONFIG.workflow;

          return (
            <List.Item className="recent-activity-item">
              <div className="recent-activity-content">
                <div className="recent-activity-header">
                  <span
                    className="recent-activity-type"
                    style={{ color: typeConfig.color }}
                  >
                    {typeConfig.icon}
                    <Text strong style={{ marginLeft: 6 }}>
                      {typeConfig.label}
                    </Text>
                  </span>
                  <Tag color={statusConfig.color}>{statusConfig.label}</Tag>
                </div>
                <Text className="recent-activity-file" ellipsis>
                  {item.file_name}
                </Text>
                {item.total_tokens > 0 && (
                  <Text type="secondary" className="recent-activity-meta">
                    <span>{item.total_tokens.toLocaleString()} tokens</span>
                    <Tooltip title="Total LLM tokens used to process this file">
                      <InfoCircleOutlined className="recent-activity-info" />
                    </Tooltip>
                  </Text>
                )}
                <Text type="secondary" className="recent-activity-time">
                  {dayjs(item.created_at).fromNow()}
                </Text>
              </div>
            </List.Item>
          );
        }}
      />
    </Card>
  );
}

RecentActivity.propTypes = {
  data: PropTypes.shape({
    activity: PropTypes.arrayOf(
      PropTypes.shape({
        id: PropTypes.string.isRequired,
        type: PropTypes.oneOf(["etl", "api", "workflow"]).isRequired,
        file_name: PropTypes.string.isRequired,
        status: PropTypes.string.isRequired,
        workflow_name: PropTypes.string,
        created_at: PropTypes.string.isRequired,
        execution_time: PropTypes.number,
        total_tokens: PropTypes.number,
      }),
    ),
  }),
  loading: PropTypes.bool,
};

RecentActivity.defaultProps = {
  data: null,
  loading: false,
};

export { RecentActivity };
