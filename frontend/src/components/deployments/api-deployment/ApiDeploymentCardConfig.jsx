import {
  ClockCircleOutlined,
  CloudDownloadOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  KeyOutlined,
  MoreOutlined,
  NotificationOutlined,
  ShareAltOutlined,
  SyncOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Button,
  Dropdown,
  Popconfirm,
  Switch,
  Tooltip,
  Typography,
} from "antd";
import { Link } from "react-router-dom";
import PropTypes from "prop-types";

import {
  copyToClipboard,
  formattedDateTime,
  shortenApiEndpoint,
} from "../../../helpers/GetStaticData";
import { StatusPills } from "../../pipelines-or-deployments/pipelines/PipelineCardConfig";
import WorkflowIcon from "../../../assets/Workflows.svg";

/**
 * Create API deployment card configuration for list mode - Row-based layout
 * No expand/collapse - all content visible directly on card
 * @return {Object} Card configuration object
 */
function createApiDeploymentCardConfig({
  setSelectedRow,
  updateStatus,
  sessionDetails,
  location,
  onEdit,
  onShare,
  onDelete,
  onViewLogs,
  onManageKeys,
  onSetupNotifications,
  onCodeSnippets,
  onDownloadPostman,
}) {
  return {
    header: {
      title: (deployment) => deployment.display_name,
      actions: [],
    },
    expandable: false, // No expand/collapse
    // Row-based list content
    listContent: (deployment, { renderActions }) => {
      const isOwner = deployment.created_by === sessionDetails?.userId;
      const email = deployment.created_by_email;
      const ownerDisplay = isOwner ? "You" : email?.split("@")[0] || "Unknown";

      // Kebab menu items for API deployments
      const kebabMenuItems = {
        items: [
          {
            key: "view-logs",
            icon: <FileSearchOutlined />,
            label: "View Logs",
            onClick: () => onViewLogs?.(deployment),
          },
          { type: "divider" },
          {
            key: "manage-keys",
            icon: <KeyOutlined />,
            label: "Manage Keys",
            onClick: () => onManageKeys?.(deployment),
          },
          {
            key: "notifications",
            icon: <NotificationOutlined />,
            label: "Notifications",
            onClick: () => onSetupNotifications?.(deployment),
          },
          { type: "divider" },
          {
            key: "code-snippets",
            icon: <CodeOutlined />,
            label: "Code Snippets",
            onClick: () => onCodeSnippets?.(deployment),
          },
          {
            key: "download-postman",
            icon: <CloudDownloadOutlined />,
            label: "Download Postman Collection",
            onClick: () => onDownloadPostman?.(deployment),
          },
        ],
      };

      return (
        <div className="card-list-content">
          {/* Header Row: Name + Actions */}
          <div className="card-list-header-row">
            <div className="card-list-title-section">
              <Tooltip title={deployment.display_name}>
                <Typography.Text className="card-list-name" strong>
                  {deployment.display_name}
                </Typography.Text>
              </Tooltip>
              {/* Description as light grey subtext - no label */}
              {deployment.description && (
                <Typography.Text
                  className="card-list-description"
                  type="secondary"
                >
                  {deployment.description}
                </Typography.Text>
              )}
            </div>

            <div className="card-list-actions">
              {/* Toggle switch */}
              <Tooltip
                title={
                  deployment.is_active
                    ? "Disable API deployment"
                    : "Enable API deployment"
                }
              >
                <Switch
                  size="small"
                  checked={deployment.is_active}
                  onChange={(checked, e) => {
                    e.stopPropagation();
                    updateStatus(deployment);
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
                      setSelectedRow(deployment);
                      onEdit?.(deployment);
                    }}
                  />
                </Tooltip>
                <Tooltip title="Share">
                  <ShareAltOutlined
                    className="action-icon-btn share-icon"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedRow(deployment);
                      onShare?.(deployment);
                    }}
                  />
                </Tooltip>
                <Popconfirm
                  title="Delete API deployment?"
                  description="This action cannot be undone."
                  onConfirm={() => {
                    setSelectedRow(deployment);
                    onDelete?.(deployment);
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

          {/* Row-based content - No SOURCE/DESTINATION for API deployments */}
          <div className="card-list-row-layout">
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
                  to={`/${sessionDetails?.orgName}/workflows/${deployment.workflow}`}
                  state={{
                    from: location?.pathname,
                    scrollToCardId: deployment.id,
                  }}
                  className="card-list-workflow-link-row"
                  onClick={(e) => e.stopPropagation()}
                >
                  {deployment.workflow_name}
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
                  {deployment.last_run_time
                    ? formattedDateTime(deployment.last_run_time)
                    : "Never"}
                </span>
              </div>
            </div>

            {/* LAST 5 RUNS row (if has data) */}
            {deployment.last_5_run_statuses?.length > 0 && (
              <div className="card-list-field-row">
                <span className="card-list-field-label">Last 5 Runs</span>
                <div className="card-list-field-value">
                  <HistoryOutlined />
                  <StatusPills
                    statuses={deployment.last_5_run_statuses}
                    executionType="API"
                    pipelineId={deployment.id}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Footer: Total Runs */}
          <div className="card-list-footer-row">
            <div className="card-list-footer-item">
              <span className="card-list-footer-label">Total Runs</span>
              <div className="card-list-footer-value">
                <SyncOutlined />
                <span>{deployment.run_count || 0}</span>
              </div>
            </div>
          </div>

          {/* API Endpoint with grey wrapper */}
          {deployment.api_endpoint && (
            <div className="card-list-endpoint-wrapper">
              <div className="card-list-endpoint-row">
                <span className="card-list-field-label">API Endpoint</span>
                <div className="card-list-endpoint-value">
                  <Tooltip
                    title={deployment.api_endpoint}
                    overlayStyle={{ maxWidth: 500 }}
                  >
                    <a
                      href={deployment.api_endpoint}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {shortenApiEndpoint(deployment.api_endpoint)}
                    </a>
                  </Tooltip>
                  <Tooltip title="Copy endpoint">
                    <Button
                      className="copy-btn-outlined"
                      icon={<CopyOutlined />}
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        copyToClipboard(deployment.api_endpoint);
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

createApiDeploymentCardConfig.propTypes = {
  setSelectedRow: PropTypes.func.isRequired,
  updateStatus: PropTypes.func.isRequired,
  sessionDetails: PropTypes.object,
  location: PropTypes.object,
  onEdit: PropTypes.func,
  onShare: PropTypes.func,
  onDelete: PropTypes.func,
  onViewLogs: PropTypes.func,
  onManageKeys: PropTypes.func,
  onSetupNotifications: PropTypes.func,
  onCodeSnippets: PropTypes.func,
  onDownloadPostman: PropTypes.func,
};

export { createApiDeploymentCardConfig };
