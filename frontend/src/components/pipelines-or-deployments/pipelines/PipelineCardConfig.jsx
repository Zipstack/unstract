import {
  CalendarOutlined,
  CheckCircleFilled,
  ClearOutlined,
  ClockCircleOutlined,
  CloseCircleFilled,
  CloudDownloadOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  KeyOutlined,
  MoreOutlined,
  NotificationOutlined,
  ScheduleOutlined,
  ShareAltOutlined,
  SyncOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Button,
  Dropdown,
  Image,
  Popconfirm,
  Switch,
  Tooltip,
  Typography,
} from "antd";
import { Link, useNavigate, useLocation } from "react-router-dom";
import cronstrue from "cronstrue";
import PropTypes from "prop-types";

import { useSessionStore } from "../../../store/session-store";
import {
  copyToClipboard,
  formattedDateTime,
  shortenApiEndpoint,
} from "../../../helpers/GetStaticData";
import WorkflowIcon from "../../../assets/Workflows.svg";

/**
 * Status badge component for displaying execution status as text badges
 * @return {JSX.Element|null} Rendered status pills or null
 */
function StatusPills({ statuses = [], executionType, pipelineId }) {
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
    <div className="status-badges-container">
      {statuses.map((run, index) => {
        const config = getStatusConfig(run.status);
        const isClickable = run.execution_id && executionType;
        const hasFileCounts = run.successful_files > 0 || run.failed_files > 0;
        return (
          <Tooltip
            key={index}
            title={
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
                  <div className="status-tooltip-hint">
                    Click to view details
                  </div>
                )}
              </div>
            }
          >
            <span
              className={`${config.className}${
                isClickable ? " status-badge-clickable" : ""
              }`}
              onClick={
                isClickable ? (e) => handleStatusClick(e, run) : undefined
              }
            >
              {config.label}
            </span>
          </Tooltip>
        );
      })}
    </div>
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
}) {
  return {
    header: {
      title: (pipeline) => pipeline.pipeline_name,
      actions: [],
    },
    expandable: false, // No expand/collapse
    // Row-based list content
    listContent: (pipeline, { renderActions }) => {
      const isOwner = pipeline.created_by === sessionDetails?.userId;
      const email = pipeline.created_by_email;
      const ownerDisplay = isOwner ? "You" : email?.split("@")[0] || "Unknown";

      // Schedule display - wrap in try-catch as cronstrue can throw on invalid cron
      let scheduleDisplay = "Not scheduled";
      if (pipeline.cron_string) {
        try {
          scheduleDisplay = cronstrue.toString(pipeline.cron_string);
        } catch {
          scheduleDisplay = pipeline.cron_string;
        }
      }

      // Kebab menu items
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
              {/* Toggle switch */}
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

              {/* Action box - Edit, Share, Delete, Kebab */}
              <div className="card-list-action-box">
                <Tooltip title="Edit">
                  <EditOutlined
                    className="action-icon-btn edit-icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedPorD(pipeline);
                      onEdit?.(pipeline);
                    }}
                  />
                </Tooltip>
                <Tooltip title="Share">
                  <ShareAltOutlined
                    className="action-icon-btn share-icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedPorD(pipeline);
                      onShare?.(pipeline);
                    }}
                  />
                </Tooltip>
                <Popconfirm
                  title="Delete pipeline?"
                  description="This action cannot be undone."
                  onConfirm={() => {
                    setSelectedPorD(pipeline);
                    onDelete?.(pipeline);
                  }}
                  onCancel={(e) => e?.stopPropagation()}
                  okText="Delete"
                  cancelText="Cancel"
                  okButtonProps={{ danger: true }}
                >
                  <Tooltip title="Delete">
                    <DeleteOutlined
                      className="action-icon-btn delete-icon"
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Tooltip>
                </Popconfirm>
                <Dropdown
                  menu={kebabMenuItems}
                  trigger={["click"]}
                  placement="bottomRight"
                >
                  <MoreOutlined
                    className="card-kebab-menu"
                    onClick={(e) => e.stopPropagation()}
                  />
                </Dropdown>
              </div>
            </div>
          </div>

          {/* Row-based content */}
          <div className="card-list-row-layout">
            {/* SOURCE row */}
            <div className="card-list-field-row">
              <span className="card-list-field-label">Source</span>
              <div className="card-list-field-value">
                <div className="card-list-field-icon">
                  <Image
                    src={pipeline.source_icon}
                    preview={false}
                    fallback="/default-connector.png"
                  />
                </div>
                <div className="card-list-field-text">
                  <span className="card-list-field-instance-name">
                    {pipeline.source_instance_name || pipeline.source_name}
                  </span>
                  {pipeline.source_instance_name && (
                    <span className="card-list-field-subtext">
                      {pipeline.source_name}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* DESTINATION row */}
            <div className="card-list-field-row">
              <span className="card-list-field-label">Destination</span>
              <div className="card-list-field-value">
                <div className="card-list-field-icon">
                  <Image
                    src={pipeline.destination_icon}
                    preview={false}
                    fallback="/default-connector.png"
                  />
                </div>
                <div className="card-list-field-text">
                  <span className="card-list-field-instance-name">
                    {pipeline.destination_instance_name ||
                      pipeline.destination_name}
                  </span>
                  {pipeline.destination_instance_name && (
                    <span className="card-list-field-subtext">
                      {pipeline.destination_name}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* WORKFLOW row */}
            <div className="card-list-field-row">
              <span className="card-list-field-label">Workflow</span>
              <div className="card-list-field-value">
                <img
                  src={WorkflowIcon}
                  alt=""
                  className="card-list-meta-icon"
                />
                <Link
                  to={`/${sessionDetails?.orgName}/workflows/${pipeline.workflow_id}`}
                  state={{
                    from: location?.pathname,
                    scrollToCardId: pipeline.id,
                  }}
                  className="card-list-workflow-link-row"
                  onClick={(e) => e.stopPropagation()}
                >
                  {pipeline.workflow_name}
                  <ExportOutlined />
                </Link>
              </div>
            </div>

            {/* OWNER row */}
            <div className="card-list-field-row">
              <span className="card-list-field-label">Owner</span>
              <div className="card-list-field-value">
                <UserOutlined />
                <Tooltip title={email}>
                  <span>{ownerDisplay}</span>
                </Tooltip>
              </div>
            </div>

            {/* LAST RUN row */}
            <div className="card-list-field-row">
              <span className="card-list-field-label">Last Run</span>
              <div className="card-list-field-value">
                <ClockCircleOutlined />
                <span>
                  {pipeline.last_run_time
                    ? formattedDateTime(pipeline.last_run_time)
                    : "Never"}
                </span>
              </div>
            </div>

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

            {/* LAST 5 RUNS row (if has data) */}
            {pipeline.last_5_run_statuses?.length > 0 && (
              <div className="card-list-field-row">
                <span className="card-list-field-label">Last 5 Runs</span>
                <div className="card-list-field-value">
                  <HistoryOutlined />
                  <StatusPills
                    statuses={pipeline.last_5_run_statuses}
                    executionType={pipelineType?.toUpperCase()}
                    pipelineId={pipeline.id}
                  />
                </div>
              </div>
            )}
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

          {/* API Endpoint with grey wrapper */}
          {pipeline.api_endpoint && (
            <div className="card-list-endpoint-wrapper">
              <div className="card-list-endpoint-row">
                <span className="card-list-field-label">API Endpoint</span>
                <div className="card-list-endpoint-value">
                  <Tooltip
                    title={pipeline.api_endpoint}
                    overlayStyle={{ maxWidth: 500 }}
                  >
                    <a
                      href={pipeline.api_endpoint}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {shortenApiEndpoint(pipeline.api_endpoint)}
                    </a>
                  </Tooltip>
                  <Tooltip title="Copy endpoint">
                    <Button
                      className="copy-btn-outlined"
                      icon={<CopyOutlined />}
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(pipeline.api_endpoint);
                      }}
                    />
                  </Tooltip>
                </div>
              </div>
            </div>
          )}
        </div>
      );
    },
    // No expandedContent - all content visible directly
    sections: [],
  };
}

export { createPipelineCardConfig, StatusPills };
