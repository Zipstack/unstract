import {
  ClockCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  HistoryOutlined,
  MoreOutlined,
  ShareAltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Popconfirm, Space, Tooltip, Typography } from "antd";
import { Link } from "react-router-dom";
import PropTypes from "prop-types";

import {
  copyToClipboard,
  formattedDateTime,
  shortenApiEndpoint,
} from "../../../helpers/GetStaticData";
import WorkflowIcon from "../../../assets/Workflows.svg";

/**
 * Reusable action box with Edit, Share, Delete icons and kebab menu
 * @return {JSX.Element} Rendered action box
 */
function CardActionBox({
  item,
  setSelectedItem,
  onEdit,
  onShare,
  onDelete,
  deleteTitle = "Delete item?",
  kebabMenuItems,
}) {
  const handleEditAction = (e) => {
    e.stopPropagation();
    setSelectedItem(item);
    onEdit?.(item);
  };

  const handleShareAction = (e) => {
    e.stopPropagation();
    setSelectedItem(item);
    onShare?.(item);
  };

  return (
    <Space className="card-list-action-box">
      <Tooltip title="Edit">
        <Button
          type="text"
          className="action-icon-btn edit-icon"
          icon={<EditOutlined />}
          onClick={handleEditAction}
        />
      </Tooltip>
      <Tooltip title="Share">
        <Button
          type="text"
          className="action-icon-btn share-icon"
          icon={<ShareAltOutlined />}
          onClick={handleShareAction}
        />
      </Tooltip>
      <Popconfirm
        title={deleteTitle}
        description="This action cannot be undone."
        onConfirm={() => {
          setSelectedItem(item);
          onDelete?.(item);
        }}
        onCancel={(e) => e?.stopPropagation()}
        okText="Delete"
        cancelText="Cancel"
        okButtonProps={{ danger: true }}
      >
        <Tooltip title="Delete">
          <Button
            type="text"
            className="action-icon-btn delete-icon"
            icon={<DeleteOutlined />}
            onClick={(e) => e.stopPropagation()}
          />
        </Tooltip>
      </Popconfirm>
      <Dropdown
        menu={kebabMenuItems}
        trigger={["click"]}
        placement="bottomRight"
      >
        <Button
          type="text"
          className="card-kebab-menu"
          icon={<MoreOutlined />}
          onClick={(e) => e.stopPropagation()}
        />
      </Dropdown>
    </Space>
  );
}

CardActionBox.propTypes = {
  item: PropTypes.object.isRequired,
  setSelectedItem: PropTypes.func.isRequired,
  onEdit: PropTypes.func,
  onShare: PropTypes.func,
  onDelete: PropTypes.func,
  deleteTitle: PropTypes.string,
  kebabMenuItems: PropTypes.object.isRequired,
};

/**
 * Reusable owner field row
 * @return {JSX.Element} Rendered owner field row
 */
function OwnerFieldRow({ item, sessionDetails }) {
  const isOwner = item.created_by === sessionDetails?.userId;
  const email = item.created_by_email;
  const ownerDisplay = isOwner ? "You" : email?.split("@")[0] || "Unknown";

  return (
    <div className="card-list-field-row">
      <span className="card-list-field-label">Owner</span>
      <div className="card-list-field-value">
        <UserOutlined />
        <Tooltip title={email}>
          <span>{ownerDisplay}</span>
        </Tooltip>
      </div>
    </div>
  );
}

OwnerFieldRow.propTypes = {
  item: PropTypes.object.isRequired,
  sessionDetails: PropTypes.object,
};

/**
 * Reusable last run field row
 * @return {JSX.Element} Rendered last run field row
 */
function LastRunFieldRow({ lastRunTime }) {
  return (
    <div className="card-list-field-row">
      <span className="card-list-field-label">Last Run</span>
      <div className="card-list-field-value">
        <ClockCircleOutlined />
        <span>{lastRunTime ? formattedDateTime(lastRunTime) : "Never"}</span>
      </div>
    </div>
  );
}

LastRunFieldRow.propTypes = {
  lastRunTime: PropTypes.string,
};

/**
 * Reusable last 5 runs field row
 * @return {JSX.Element|null} Rendered last 5 runs field row or null
 */
function Last5RunsFieldRow({
  statuses,
  executionType,
  itemId,
  StatusPillsComponent,
  listContext,
}) {
  if (!statuses?.length) return null;

  return (
    <div className="card-list-field-row">
      <span className="card-list-field-label">Last 5 Runs</span>
      <div className="card-list-field-value">
        <HistoryOutlined />
        <StatusPillsComponent
          statuses={statuses}
          executionType={executionType}
          pipelineId={itemId}
          listContext={listContext}
        />
      </div>
    </div>
  );
}

Last5RunsFieldRow.propTypes = {
  statuses: PropTypes.array,
  executionType: PropTypes.string,
  itemId: PropTypes.string,
  StatusPillsComponent: PropTypes.elementType.isRequired,
  listContext: PropTypes.object,
};

/**
 * Reusable workflow link field row
 * @return {JSX.Element} Rendered workflow field row
 */
function WorkflowFieldRow({
  workflowId,
  workflowName,
  sessionDetails,
  location,
  itemId,
}) {
  const orgName = sessionDetails?.orgName;

  // Guard against undefined orgName to prevent malformed URLs
  if (!orgName) {
    return (
      <div className="card-list-field-row">
        <span className="card-list-field-label">Workflow</span>
        <div className="card-list-field-value">
          <img src={WorkflowIcon} alt="" className="card-list-meta-icon" />
          <span className="card-list-workflow-link-row">{workflowName}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card-list-field-row">
      <span className="card-list-field-label">Workflow</span>
      <div className="card-list-field-value">
        <img src={WorkflowIcon} alt="" className="card-list-meta-icon" />
        <Link
          to={`/${orgName}/workflows/${workflowId}`}
          state={{
            from: location?.pathname,
            scrollToCardId: itemId,
          }}
          className="card-list-workflow-link-row"
          onClick={(e) => e.stopPropagation()}
        >
          {workflowName}
          <ExportOutlined />
        </Link>
      </div>
    </div>
  );
}

WorkflowFieldRow.propTypes = {
  workflowId: PropTypes.string.isRequired,
  workflowName: PropTypes.string.isRequired,
  sessionDetails: PropTypes.object,
  location: PropTypes.object,
  itemId: PropTypes.string,
};

/**
 * Reusable API endpoint section
 * @return {JSX.Element|null} Rendered API endpoint section or null
 */
function ApiEndpointSection({ apiEndpoint }) {
  if (!apiEndpoint) return null;

  return (
    <div className="card-list-endpoint-wrapper">
      <div className="card-list-endpoint-row">
        <span className="card-list-field-label">API Endpoint</span>
        <div className="card-list-endpoint-value">
          <Tooltip title={apiEndpoint} overlayStyle={{ maxWidth: 500 }}>
            <a
              href={apiEndpoint}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              {shortenApiEndpoint(apiEndpoint)}
            </a>
          </Tooltip>
          <Tooltip title="Copy endpoint">
            <Button
              className="copy-btn-outlined"
              icon={<CopyOutlined />}
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                copyToClipboard(apiEndpoint);
              }}
            />
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

ApiEndpointSection.propTypes = {
  apiEndpoint: PropTypes.string,
};

/**
 * Reusable card header row with title and actions
 * @return {JSX.Element} Rendered header row
 */
function CardHeaderRow({ title, description, children }) {
  return (
    <div className="card-list-header-row">
      <div className="card-list-title-section">
        <Tooltip title={title}>
          <Typography.Text className="card-list-name" strong>
            {title}
          </Typography.Text>
        </Tooltip>
        {description && (
          <Typography.Text className="card-list-description" type="secondary">
            {description}
          </Typography.Text>
        )}
      </div>
      {children}
    </div>
  );
}

CardHeaderRow.propTypes = {
  title: PropTypes.string.isRequired,
  description: PropTypes.string,
  children: PropTypes.node,
};

export {
  CardActionBox,
  OwnerFieldRow,
  LastRunFieldRow,
  Last5RunsFieldRow,
  WorkflowFieldRow,
  ApiEndpointSection,
  CardHeaderRow,
};
