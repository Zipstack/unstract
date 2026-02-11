import {
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
import { Image, Space, Switch, Tag, Tooltip, Typography } from "antd";
import { useNavigate, useLocation } from "react-router-dom";
import cronstrue from "cronstrue";
import PropTypes from "prop-types";

import { useSessionStore } from "../../../store/session-store";
import { formattedDateTime } from "../../../helpers/GetStaticData";
import {
  CardActionBox,
  OwnerFieldRow,
  LastRunFieldRow,
  Last5RunsFieldRow,
  WorkflowFieldRow,
  ApiEndpointSection,
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
        }
      );
    }
  };

  const getStatusConfig = (status) => {
    const statusLower = (status || "").toLowerCase();
    switch (statusLower) {
      case "completed":
      case "success":
        return { label: "SUCCESS", className: "status-badge success" };
      case "error":
      case "failed":
      case "failure":
        return { label: "ERROR", className: "status-badge error" };
      case "partial_success":
      case "partial success":
        return { label: "PARTIAL", className: "status-badge partial_success" };
      case "executing":
      case "processing":
      case "running":
        return { label: "EXECUTING", className: "status-badge executing" };
      case "pending":
        return { label: "PENDING", className: "status-badge pending" };
      case "stopped":
        return { label: "STOPPED", className: "status-badge stopped" };
      default:
        return {
          label: status?.toUpperCase() || "UNKNOWN",
          className: "status-badge unknown",
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
          <div className="status-tooltip-content">
            {hasFileCounts && (
              <div className="status-tooltip-counts">
                <span className="status-tooltip-count success">
                  <CheckCircleFilled /> {run.successful_files}
                </span>
                <span className="status-tooltip-count error">
                  <CloseCircleFilled /> {run.failed_files}
                </span>
              </div>
            )}
            {run.timestamp && (
              <div className="status-tooltip-timestamp">
                {formattedDateTime(run.timestamp)}
              </div>
            )}
            {isClickable && (
              <div className="status-tooltip-hint">Click to view details</div>
            )}
          </div>
        );

        if (isClickable) {
          return (
            <Tooltip key={key} title={tooltipContent}>
              <Tag
                className={`${config.className} status-badge-clickable`}
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
            <Tag className={config.className}>{config.label}</Tag>
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
    })
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
    <div className="card-list-field-row">
      <span className="card-list-field-label">{label}</span>
      <div className="card-list-field-value">
        <div className="card-list-field-icon">
          <Image src={icon} preview={false} fallback="/default-connector.png" />
        </div>
        <div className="card-list-field-text">
          <span className="card-list-field-instance-name">
            {instanceName || connectorName}
          </span>
          {instanceName && (
            <span className="card-list-field-subtext">{connectorName}</span>
          )}
        </div>
      </div>
    </div>
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

            <div className="card-list-actions">
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
            </div>
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
              <div className="card-list-field-row">
                <span className="card-list-field-label">Next Run At</span>
                <div className="card-list-field-value">
                  <ScheduleOutlined />
                  <span>{formattedDateTime(pipeline.next_run_time)}</span>
                </div>
              </div>
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
          <div className="card-list-footer-row">
            <div className="card-list-footer-item">
              <CalendarOutlined />
              <span className="card-list-footer-label">Schedule</span>
              <span>{scheduleDisplay}</span>
            </div>
            <div className="card-list-footer-item">
              <SyncOutlined />
              <span className="card-list-footer-label">Total Runs</span>
              <span>{pipeline.run_count || 0}</span>
            </div>
          </div>

          <ApiEndpointSection apiEndpoint={pipeline.api_endpoint} />
        </div>
      );
    },
    sections: [],
  };
}

export { createPipelineCardConfig, StatusPills };
