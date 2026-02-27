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
import {
  Avatar,
  Button,
  Card,
  Dropdown,
  Flex,
  Popconfirm,
  Space,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";
import WorkflowIcon from "../../../assets/Workflows.svg";
import {
  copyToClipboard,
  formattedDateTime,
  shortenApiEndpoint,
} from "../../../helpers/GetStaticData";

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
      <Button
        type="text"
        className="action-icon-btn edit-icon"
        icon={<EditOutlined />}
        onClick={handleEditAction}
      />
      <Button
        type="text"
        className="action-icon-btn share-icon"
        icon={<ShareAltOutlined />}
        onClick={handleShareAction}
      />
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
        <Button
          type="text"
          className="action-icon-btn delete-icon"
          icon={<DeleteOutlined />}
          onClick={(e) => e.stopPropagation()}
        />
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
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        Owner
      </Typography.Text>
      <Space size={10} className="card-list-field-value">
        <UserOutlined />
        <Tooltip title={email}>
          <Typography.Text>{ownerDisplay}</Typography.Text>
        </Tooltip>
      </Space>
    </Flex>
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
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        Last Run
      </Typography.Text>
      <Space size={10} className="card-list-field-value">
        <ClockCircleOutlined />
        <Typography.Text>
          {lastRunTime ? formattedDateTime(lastRunTime) : "Never"}
        </Typography.Text>
      </Space>
    </Flex>
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
  if (!statuses?.length) {
    return null;
  }

  return (
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        Last 5 Runs
      </Typography.Text>
      <Space size={10} className="card-list-field-value">
        <HistoryOutlined />
        <StatusPillsComponent
          statuses={statuses}
          executionType={executionType}
          pipelineId={itemId}
          listContext={listContext}
        />
      </Space>
    </Flex>
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
  listContext,
}) {
  const orgName = sessionDetails?.orgName;

  // Guard against undefined orgName to prevent malformed URLs
  if (!orgName) {
    return (
      <Flex align="center" className="card-list-field-row">
        <Typography.Text type="secondary" className="card-list-field-label">
          Workflow
        </Typography.Text>
        <Space size={10} className="card-list-field-value">
          <Avatar
            src={WorkflowIcon}
            size={14}
            shape="square"
            className="card-list-meta-icon"
          />
          <Typography.Text className="card-list-workflow-link-row">
            {workflowName}
          </Typography.Text>
        </Space>
      </Flex>
    );
  }

  return (
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        Workflow
      </Typography.Text>
      <Space size={10} className="card-list-field-value">
        <Avatar
          src={WorkflowIcon}
          size={14}
          shape="square"
          className="card-list-meta-icon"
        />
        <Link
          to={`/${orgName}/workflows/${workflowId}`}
          state={{
            from: location?.pathname,
            scrollToCardId: itemId,
            page: listContext?.page,
            pageSize: listContext?.pageSize,
            searchTerm: listContext?.searchTerm,
          }}
          className="card-list-workflow-link-row"
          onClick={(e) => e.stopPropagation()}
        >
          {workflowName}
          <ExportOutlined />
        </Link>
      </Space>
    </Flex>
  );
}

WorkflowFieldRow.propTypes = {
  workflowId: PropTypes.string.isRequired,
  workflowName: PropTypes.string.isRequired,
  sessionDetails: PropTypes.object,
  location: PropTypes.object,
  itemId: PropTypes.string,
  listContext: PropTypes.object,
};

/**
 * Reusable API endpoint section
 * @return {JSX.Element|null} Rendered API endpoint section or null
 */
function ApiEndpointSection({ apiEndpoint }) {
  if (!apiEndpoint) {
    return null;
  }

  // Validate URL scheme to prevent javascript: or other malicious protocols
  const isValidUrl = (() => {
    try {
      const parsed = new URL(apiEndpoint, window.location.origin);
      return ["http:", "https:"].includes(parsed.protocol);
    } catch {
      return false;
    }
  })();

  return (
    <div className="card-list-endpoint-wrapper">
      <Card size="small" className="card-list-endpoint-row">
        <Flex align="center" gap={12}>
          <Typography.Text type="secondary" className="card-list-field-label">
            API Endpoint
          </Typography.Text>
          <div className="card-list-endpoint-value">
            <Tooltip title={apiEndpoint} overlayStyle={{ maxWidth: 500 }}>
              {isValidUrl ? (
                <Typography.Link
                  href={apiEndpoint}
                  target="_blank"
                  onClick={(e) => e.stopPropagation()}
                >
                  {shortenApiEndpoint(apiEndpoint)}
                </Typography.Link>
              ) : (
                <Typography.Text>
                  {shortenApiEndpoint(apiEndpoint)}
                </Typography.Text>
              )}
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
        </Flex>
      </Card>
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
    <Flex
      justify="space-between"
      align="center"
      className="card-list-header-row"
    >
      <Flex vertical gap={4} className="card-list-title-section">
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
      </Flex>
      {children}
    </Flex>
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
