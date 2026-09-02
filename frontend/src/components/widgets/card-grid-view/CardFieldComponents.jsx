import {
  Clock,
  Copy,
  EllipsisVertical,
  ExternalLink,
  History,
  Pencil,
  Share2,
  Trash2,
  User,
} from "lucide-react";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Flex, Space } from "@/components/ui/shims/antd-layout";
import { Avatar } from "@/components/ui/shims/antd-leaves";
import {
  Dropdown,
  Popconfirm,
  Tooltip,
} from "@/components/ui/shims/antd-overlays";
import { Card } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";
import WorkflowIcon from "../../../assets/Workflows.svg";
import {
  copyToClipboard,
  formattedDateTime,
  shortenApiEndpoint,
} from "../../../helpers/GetStaticData";
import { canEditResource } from "../../../helpers/resourceAccess";
import { useSessionStore } from "../../../store/session-store";

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
  /**
   * Names the kind of card this box sits on ("api-deployment", "pipeline").
   * Combined with the item's id it yields `api-deployment-edit-<id>`, which is
   * the only way to tell one card's Edit from another's.
   */
  testIdPrefix,
}) {
  const { sessionDetails } = useSessionStore();
  // Sharing grants read only: no edit, no delete. Sharing onward stays
  // available -- see the Share button below.
  const canEdit = canEditResource(item, sessionDetails);
  const testId = (suffix) =>
    testIdPrefix ? `${testIdPrefix}-${suffix}-${item?.id}` : undefined;
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
      {canEdit && (
        <Button
          type="text"
          className="action-icon-btn edit-icon"
          data-testid={testId("edit")}
          icon={<Pencil />}
          onClick={handleEditAction}
        />
      )}
      {/* Sharing stays open to shared users: they may pass access on to a
          group they belong to, or to a user in the same organisation. */}
      <Button
        type="text"
        className="action-icon-btn share-icon"
        data-testid={testId("share")}
        icon={<Share2 />}
        onClick={handleShareAction}
      />
      {canEdit && (
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
          /*
           * Not keyed by item: only one confirm panel can be open at a time, so
           * the id identifies the KIND of thing being deleted, which is what a
           * test needs to know before clicking through.
           */
          data-testid={
            testIdPrefix ? `${testIdPrefix}-delete-confirm` : undefined
          }
        >
          <Button
            type="text"
            className="action-icon-btn delete-icon"
            data-testid={testId("delete")}
            icon={<Trash2 />}
            onClick={(e) => e.stopPropagation()}
          />
        </Popconfirm>
      )}
      <Dropdown
        menu={kebabMenuItems}
        trigger={["click"]}
        placement="bottomRight"
        data-testid={testId("kebab-menu")}
      >
        <Button
          type="text"
          className="card-kebab-menu"
          data-testid={testId("kebab-btn")}
          icon={<EllipsisVertical />}
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
  testIdPrefix: PropTypes.string,
};

/**
 * Reusable owner field row
 * @return {JSX.Element} Rendered owner field row
 */
function OwnerFieldRow({ item, sessionDetails, onManageCoOwners }) {
  const isOwner = item?.is_owner ?? item.created_by === sessionDetails?.userId;
  const email = item.created_by_email;
  const name = isOwner ? "Me" : email?.split("@")[0] || "Unknown";
  const extra =
    item?.co_owners_count > 1 ? ` +${item.co_owners_count - 1}` : "";
  const ownerDisplay = `${name}${extra}`;

  const ownerContent = (
    <Space size={10} className="card-list-field-value">
      <User />
      <Tooltip title={email}>
        <Typography.Text>{ownerDisplay}</Typography.Text>
      </Tooltip>
    </Space>
  );

  return (
    <Flex align="center" className="card-list-field-row">
      <Typography.Text type="secondary" className="card-list-field-label">
        Owner
      </Typography.Text>
      {onManageCoOwners ? (
        <Tooltip title="Manage Co-Owners">
          <button
            type="button"
            className="card-owner-clickable"
            onClick={(e) => {
              e.stopPropagation();
              onManageCoOwners();
            }}
          >
            {ownerContent}
          </button>
        </Tooltip>
      ) : (
        ownerContent
      )}
    </Flex>
  );
}

OwnerFieldRow.propTypes = {
  item: PropTypes.object.isRequired,
  sessionDetails: PropTypes.object,
  onManageCoOwners: PropTypes.func,
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
        <Clock />
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
        <History />
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
          <ExternalLink />
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

  return (
    <div className="card-list-endpoint-wrapper">
      <Card size="small" className="card-list-endpoint-row">
        <Flex align="center" gap={12}>
          <Typography.Text type="secondary" className="card-list-field-label">
            API Endpoint
          </Typography.Text>
          <div className="card-list-endpoint-value">
            <Tooltip title={apiEndpoint} overlayStyle={{ maxWidth: 500 }}>
              <Typography.Text>
                {shortenApiEndpoint(apiEndpoint)}
              </Typography.Text>
            </Tooltip>
            <Tooltip title="Copy endpoint">
              <Button
                className="copy-btn-outlined"
                icon={<Copy />}
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
  ApiEndpointSection,
  CardActionBox,
  CardHeaderRow,
  Last5RunsFieldRow,
  LastRunFieldRow,
  OwnerFieldRow,
  WorkflowFieldRow,
};
