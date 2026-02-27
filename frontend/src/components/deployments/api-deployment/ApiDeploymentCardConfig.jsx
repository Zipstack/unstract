import {
  CloudDownloadOutlined,
  CodeOutlined,
  FileSearchOutlined,
  KeyOutlined,
  NotificationOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { Switch, Tooltip } from "antd";
import PropTypes from "prop-types";

import { StatusPills } from "../../pipelines-or-deployments/pipelines/PipelineCardConfig";
import {
  ApiEndpointSection,
  CardActionBox,
  CardHeaderRow,
  Last5RunsFieldRow,
  LastRunFieldRow,
  OwnerFieldRow,
  WorkflowFieldRow,
} from "../../widgets/card-grid-view/CardFieldComponents";

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
  listContext,
}) {
  return {
    header: {
      title: (deployment) => deployment.display_name,
      actions: [],
    },
    expandable: false,
    listContent: (deployment) => {
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
          <CardHeaderRow
            title={deployment.display_name}
            description={deployment.description}
          >
            <div className="card-list-actions">
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
              <CardActionBox
                item={deployment}
                setSelectedItem={setSelectedRow}
                onEdit={onEdit}
                onShare={onShare}
                onDelete={onDelete}
                deleteTitle="Delete API deployment?"
                kebabMenuItems={kebabMenuItems}
              />
            </div>
          </CardHeaderRow>

          <div className="card-list-row-layout">
            <WorkflowFieldRow
              workflowId={deployment.workflow}
              workflowName={deployment.workflow_name}
              sessionDetails={sessionDetails}
              location={location}
              itemId={deployment.id}
              listContext={listContext}
            />
            <OwnerFieldRow item={deployment} sessionDetails={sessionDetails} />
            <LastRunFieldRow lastRunTime={deployment.last_run_time} />
            <Last5RunsFieldRow
              statuses={deployment.last_5_run_statuses}
              executionType="API"
              itemId={deployment.id}
              StatusPillsComponent={StatusPills}
              listContext={listContext}
            />
          </div>

          <div className="card-list-footer-row">
            <div className="card-list-footer-item">
              <span className="card-list-footer-label">Total Runs</span>
              <div className="card-list-footer-value">
                <SyncOutlined />
                <span>{deployment.run_count || 0}</span>
              </div>
            </div>
          </div>

          <ApiEndpointSection apiEndpoint={deployment.api_endpoint} />
        </div>
      );
    },
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
  listContext: PropTypes.object,
};

export { createApiDeploymentCardConfig };
