import {
  AppstoreOutlined,
  CalendarOutlined,
  CheckCircleFilled,
  ClearOutlined,
  CloseCircleFilled,
  CloudDownloadOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  KeyOutlined,
  NotificationOutlined,
  ScheduleOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { Avatar, Flex, Space, Switch, Tag, Tooltip, Typography } from "antd";
import cronstrue from "cronstrue";
import PropTypes from "prop-types";
import { useLocation, useNavigate } from "react-router-dom";
import { formattedDateTime } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
import {
  ApiEndpointSection,
  CardActionBox,
  Last5RunsFieldRow,
  LastRunFieldRow,
  OwnerFieldRow,
  WorkflowFieldRow,
} from "../../widgets/card-grid-view/CardFieldComponents";

/**
 * Status badge component for displaying execution status as text badges
 * @return {JSX.Element|null} Rendered status pills or null
 */
function StatusPills({
  statuses = [],
  executionType,
  pipelineId,
  listContext = {},
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionDetails } = useSessionStore();

  if (!statuses || statuses.length === 0) {
    return null;
  }

  const handleStatusClick = (e, run) => {
    e.stopPropagation();
    if (run.execution_id && executionType && sessionDetails?.orgName) {
      navigate(
        `/${sessionDetails.orgName}/logs/${executionType}/${run.execution_id}`,
        {
          state: {
            from: location.pathname,
            scrollToCardId: pipelineId,
            // Include list context for full restoration on back navigation
            page: listContext.page,
            pageSize: listContext.pageSize,
            searchTerm: listContext.searchTerm,
          },
        },
      );
    }
  };

  const getStatusConfig = (status) => {
    const statusLower = (status || "").toLowerCase();
    switch (statusLower) {
      case "completed":
      case "success":
        return { label: "SUCCESS", color: "success" };
      case "error":
      case "failed":
      case "failure":
        return { label: "ERROR", color: "error" };
      case "partial_success":
      case "partial success":
        return { label: "PARTIAL", color: "warning" };
      case "executing":
      case "processing":
      case "running":
        return { label: "EXECUTING", color: "processing" };
      case "pending":
        return { label: "PENDING", color: "default" };
      case "stopped":
        return { label: "STOPPED", color: "default" };
      default:
        return {
          label: status?.toUpperCase() || "UNKNOWN",
          color: "default",
        };
    }
  };

  return (
    <Space className="status-badges-container" size={6} wrap>
      {statuses.map((run, index) => {
        const config = getStatusConfig(run.status);
        const isClickable = run.execution_id && executionType;
        const hasFileCounts = run.successful_files > 0 || run.failed_files > 0;
        // Use execution_id for unique key, fallback to timestamp, then index
        const key =
          run.execution_id || run.timestamp || `${config.label}-${index}`;
        const tooltipContent = (
          <Space
            direction="vertical"
            size={4}
            className="status-tooltip-content"
          >
            {hasFileCounts && (
              <Space size={12} className="status-tooltip-counts">
                <Typography.Text className="status-tooltip-count success">
                  <CheckCircleFilled /> {run.successful_files}
                </Typography.Text>
                <Typography.Text className="status-tooltip-count error">
                  <CloseCircleFilled /> {run.failed_files}
                </Typography.Text>
              </Space>
            )}
            {run.timestamp && (
              <Typography.Text className="status-tooltip-timestamp">
                {formattedDateTime(run.timestamp)}
              </Typography.Text>
            )}
            {isClickable && (
              <Typography.Text className="status-tooltip-hint">
                Click to view details
              </Typography.Text>
            )}
          </Space>
        );

        if (isClickable) {
          return (
            <Tooltip key={key} title={tooltipContent}>
              <Tag
                color={config.color}
                className="status-badge status-badge-clickable"
                onClick={(e) => handleStatusClick(e, run)}
                tabIndex={0}
                role="button"
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleStatusClick(e, run);
                  }
                }}
              >
                {config.label}
              </Tag>
            </Tooltip>
          );
        }

        return (
          <Tooltip key={key} title={tooltipContent}>
            <Tag color={config.color} className="status-badge">
              {config.label}
            </Tag>
          </Tooltip>
        );
      })}
    </Space>
  );
}

StatusPills.propTypes = {
  statuses: PropTypes.arrayOf(
    PropTypes.shape({
      status: PropTypes.string,
      timestamp: PropTypes.string,
      execution_id: PropTypes.string,
    }),
  ),
  executionType: PropTypes.string,
  pipelineId: PropTypes.string,
  listContext: PropTypes.object,
};

/**
 * Source/Destination connector field row
 * @return {JSX.Element} Rendered connector field row
 */
function ConnectorFieldRow({ label, icon, instanceName, connectorName }) {
  return (
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        {label}
      </Typography.Text>
      <Space size={10} className="card-list-field-value">
        <Avatar
          src={icon}
          size={32}
          shape="square"
          icon={<AppstoreOutlined />}
        />
        <Flex vertical gap={2} className="card-list-field-text">
          <Typography.Text className="card-list-field-instance-name">
            {instanceName || connectorName}
          </Typography.Text>
          {instanceName && (
            <Typography.Text
              type="secondary"
              className="card-list-field-subtext"
            >
              {connectorName}
            </Typography.Text>
          )}
        </Flex>
      </Space>
    </Flex>
  );
}

ConnectorFieldRow.propTypes = {
  label: PropTypes.string.isRequired,
  icon: PropTypes.string,
  instanceName: PropTypes.string,
  connectorName: PropTypes.string,
};

/**
 * Create pipeline card configuration for list mode - Row-based layout
 * No expand/collapse - all content visible directly on card
 * @return {Object} Card configuration object
 */
function createPipelineCardConfig({
  setSelectedPorD,
  handleEnablePipeline,
  sessionDetails,
  location,
  onEdit,
  onShare,
  onDelete,
  onViewLogs,
  onViewFileHistory,
  onClearFileHistory,
  onSyncNow,
  onManageKeys,
  onSetupNotifications,
  onDownloadPostman,
  isClearingFileHistory,
  pipelineType,
  listContext,
}) {
  return {
    header: {
      title: (pipeline) => pipeline.pipeline_name,
      actions: [],
    },
    expandable: false,
    listContent: (pipeline) => {
      // Schedule display
      let scheduleDisplay = "Not scheduled";
      if (pipeline.cron_string) {
        try {
          scheduleDisplay = cronstrue.toString(pipeline.cron_string);
        } catch {
          scheduleDisplay = pipeline.cron_string;
        }
      }

      const kebabMenuItems = {
        items: [
          {
            key: "view-logs",
            icon: <FileSearchOutlined />,
            label: "View Logs",
            onClick: () => onViewLogs?.(pipeline),
          },
          {
            key: "file-history",
            icon: <HistoryOutlined />,
            label: "View File History",
            onClick: () => onViewFileHistory?.(pipeline),
          },
          {
            key: "clear-history",
            icon: <ClearOutlined />,
            label: isClearingFileHistory ? "Clearing..." : "Clear File History",
            disabled: isClearingFileHistory,
            onClick: () => onClearFileHistory?.(pipeline),
          },
          { type: "divider" },
          {
            key: "sync-now",
            icon: <SyncOutlined />,
            label: "Sync Now",
            onClick: () => onSyncNow?.(pipeline),
          },
          { type: "divider" },
          {
            key: "manage-keys",
            icon: <KeyOutlined />,
            label: "Manage Keys",
            onClick: () => onManageKeys?.(pipeline),
          },
          {
            key: "notifications",
            icon: <NotificationOutlined />,
            label: "Notifications",
            onClick: () => onSetupNotifications?.(pipeline),
          },
          { type: "divider" },
          {
            key: "download-postman",
            icon: <CloudDownloadOutlined />,
            label: "Download Postman Collection",
            onClick: () => onDownloadPostman?.(pipeline),
          },
        ],
      };

      return (
        <div className="card-list-content">
          {/* Header Row: Name + Actions */}
          <div className="card-list-header-row">
            <Tooltip title={pipeline.pipeline_name}>
              <Typography.Text className="card-list-name" strong>
                {pipeline.pipeline_name}
              </Typography.Text>
            </Tooltip>

            <Space size={16} className="card-list-actions">
              <Tooltip
                title={pipeline.active ? "Disable pipeline" : "Enable pipeline"}
              >
                <Switch
                  size="small"
                  checked={pipeline.active}
                  onChange={(checked, e) => {
                    e.stopPropagation();
                    handleEnablePipeline(checked, pipeline.id);
                  }}
                />
              </Tooltip>
              <CardActionBox
                item={pipeline}
                setSelectedItem={setSelectedPorD}
                onEdit={onEdit}
                onShare={onShare}
                onDelete={onDelete}
                deleteTitle="Delete pipeline?"
                kebabMenuItems={kebabMenuItems}
              />
            </Space>
          </div>

          {/* Row-based content */}
          <div className="card-list-row-layout">
            <ConnectorFieldRow
              label="Source"
              icon={pipeline.source_icon}
              instanceName={pipeline.source_instance_name}
              connectorName={pipeline.source_name}
            />
            <ConnectorFieldRow
              label="Destination"
              icon={pipeline.destination_icon}
              instanceName={pipeline.destination_instance_name}
              connectorName={pipeline.destination_name}
            />
            <WorkflowFieldRow
              workflowId={pipeline.workflow_id}
              workflowName={pipeline.workflow_name}
              sessionDetails={sessionDetails}
              location={location}
              itemId={pipeline.id}
              listContext={listContext}
            />
            <OwnerFieldRow item={pipeline} sessionDetails={sessionDetails} />
            <LastRunFieldRow lastRunTime={pipeline.last_run_time} />

            {/* NEXT RUN AT row (only if scheduled) */}
            {pipeline.next_run_time && (
              <Flex align="center" className="card-list-field-row">
                <Typography.Text
                  type="secondary"
                  className="card-list-field-label"
                >
                  Next Run At
                </Typography.Text>
                <Space size={10} className="card-list-field-value">
                  <ScheduleOutlined />
                  <Typography.Text>
                    {formattedDateTime(pipeline.next_run_time)}
                  </Typography.Text>
                </Space>
              </Flex>
            )}

            <Last5RunsFieldRow
              statuses={pipeline.last_5_run_statuses}
              executionType={pipelineType?.toUpperCase()}
              itemId={pipeline.id}
              StatusPillsComponent={StatusPills}
              listContext={listContext}
            />
          </div>

          {/* Footer: Schedule | Total Runs */}
          <Flex align="center" gap={32} className="card-list-footer-row">
            <Space size={10} className="card-list-footer-item">
              <CalendarOutlined />
              <Typography.Text
                type="secondary"
                className="card-list-footer-label"
              >
                Schedule
              </Typography.Text>
              <Typography.Text>{scheduleDisplay}</Typography.Text>
            </Space>
            <Space size={10} className="card-list-footer-item">
              <SyncOutlined />
              <Typography.Text
                type="secondary"
                className="card-list-footer-label"
              >
                Total Runs
              </Typography.Text>
              <Typography.Text>{pipeline.run_count || 0}</Typography.Text>
            </Space>
          </Flex>

          <ApiEndpointSection apiEndpoint={pipeline.api_endpoint} />
        </div>
      );
    },
    sections: [],
  };
}

export { createPipelineCardConfig, StatusPills };
