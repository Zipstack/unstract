import {
  Avatar,
  Flex,
  Image,
  List,
  Popconfirm,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import "./ListView.css";
import {
  DeleteOutlined,
  EditOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  ShareAltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import moment from "moment";
import { useNavigate } from "react-router-dom";

import { formattedDateTime } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";

// Rows are presence-keyed: pages whose APIs don't return a field simply
// don't show it (e.g. model is adapter-only, prompt_count is prompt studio).
const renderItemMetadata = (item) => (
  <div>
    {item?.created_at && (
      <div>Created: {formattedDateTime(item.created_at)}</div>
    )}
    {item?.modified_at && (
      <div>Modified: {formattedDateTime(item.modified_at)}</div>
    )}
    {item?.model && <div>Model: {item.model}</div>}
    {item?.prompt_count !== undefined && (
      <div>Prompts: {item.prompt_count}</div>
    )}
  </div>
);

function ListView({
  listOfTools,
  handleEdit,
  handleDelete,
  handleShare,
  titleProp,
  descriptionProp,
  iconProp,
  idProp,
  centered,
  isClickable = true,
  showOwner = true,
  type,
}) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const handleDeleteClick = (event, tool) => {
    event.stopPropagation(); // Stop propagation to prevent list item click
    handleDelete(event, tool);
  };

  const handleShareClick = (event, tool, isEdit) => {
    event.stopPropagation(); // Stop propagation to prevent list item click
    handleShare(event, tool, isEdit);
  };

  const renderTitle = (item) => {
    let title = null;
    if (iconProp && item[iconProp].length > 4) {
      title = (
        <div className="adapter-cover-img">
          <Image src={item[iconProp]} preview={false} className="fit-cover" />
          <Typography.Text className="adapters-list-title">
            {item[titleProp]}
          </Typography.Text>
        </div>
      );
    } else if (iconProp) {
      title = (
        <Typography.Text className="adapters-list-title">
          {`${item[iconProp]} ${item[titleProp]}`}
        </Typography.Text>
      );
    } else {
      title = (
        <Typography.Text className="adapters-list-title">
          {item[titleProp]}
        </Typography.Text>
      );
    }

    return title;
  };

  const renderMeta = (item) => {
    if (!showOwner && !item?.modified_at) {
      return null;
    }
    return (
      <div
        className="list-view-meta"
        onClick={(event) => event.stopPropagation()}
        role="none"
      >
        {showOwner && (
          <div className="adapters-list-profile-container">
            <Avatar
              size={20}
              className="adapters-list-user-avatar"
              icon={<UserOutlined />}
            />
            <Typography.Text disabled className="adapters-list-user-prefix">
              Owned By:
            </Typography.Text>
            <Typography.Text
              className="shared-username"
              ellipsis={{ tooltip: true }}
            >
              {item?.created_by_email
                ? item?.created_by_email === sessionDetails.email
                  ? "Me"
                  : item?.created_by_email
                : "-"}
            </Typography.Text>
          </div>
        )}
        {item?.modified_at && (
          <div className="adapters-list-modified-container">
            <Typography.Text
              type="secondary"
              className="adapters-list-modified-text"
            >
              Updated {moment(item.modified_at).fromNow()}
            </Typography.Text>
            <Tooltip title={renderItemMetadata(item)}>
              <InfoCircleOutlined
                className="adapters-list-info-icon"
                aria-label="Creation and modification details"
              />
            </Tooltip>
          </div>
        )}
      </div>
    );
  };

  const renderActions = (item) => (
    <div
      className="action-button-container"
      onClick={(event) => event.stopPropagation()}
      role="none"
    >
      <Tooltip title={item?.is_deprecated ? "This adapter is deprecated" : ""}>
        <EditOutlined
          key={`${item.id}-edit`}
          onClick={(event) => handleEdit(event, item)}
          className={`action-icon-buttons edit-icon ${
            item?.is_deprecated ? "disabled-icon" : ""
          }`}
          style={{
            cursor: item?.is_deprecated ? "not-allowed" : "pointer",
            opacity: item?.is_deprecated ? 0.4 : 1,
          }}
        />
      </Tooltip>
      {handleShare && (
        <Tooltip
          title={item?.is_deprecated ? "This adapter is deprecated" : ""}
        >
          <ShareAltOutlined
            key={`${item.id}-share`}
            className={`action-icon-buttons share-icon ${
              item?.is_deprecated ? "disabled-icon" : ""
            }`}
            onClick={(event) => handleShareClick(event, item, true)}
            style={{
              cursor: item?.is_deprecated ? "not-allowed" : "pointer",
              opacity: item?.is_deprecated ? 0.4 : 1,
            }}
          />
        </Tooltip>
      )}
      <Popconfirm
        key={`${item.id}-delete`}
        title={`Delete the ${type}`}
        description={`Are you sure to delete ${item[titleProp]}`}
        okText="Yes"
        cancelText="No"
        icon={<QuestionCircleOutlined />}
        onConfirm={(event) => {
          handleDeleteClick(event, item);
        }}
      >
        <Typography.Text>
          <DeleteOutlined className="action-icon-buttons delete-icon" />
        </Typography.Text>
      </Popconfirm>
    </div>
  );

  return (
    <List
      size="large"
      dataSource={listOfTools}
      style={{ marginInline: "4px" }}
      pagination={{
        position: "bottom",
        align: "end",
        size: "small",
      }}
      className="list-view-wrapper"
      renderItem={(item) => {
        return (
          <List.Item
            key={item?.id}
            onClick={(event) => {
              isClickable
                ? navigate(`${item[idProp]}`)
                : handleShareClick(event, item, false);
            }}
            className={`cur-pointer ${centered ? "centered" : ""}`}
          >
            <Flex
              gap={24}
              align="center"
              justify="space-between"
              className="list-view-row"
            >
              <div className="list-view-left">
                {renderTitle(item)}
                {item[descriptionProp] ? (
                  <Typography.Paragraph
                    type="secondary"
                    ellipsis={{ rows: 1, tooltip: true }}
                    className="list-view-description"
                  >
                    {item[descriptionProp]}
                  </Typography.Paragraph>
                ) : null}
              </div>
              {renderMeta(item)}
              {renderActions(item)}
            </Flex>
          </List.Item>
        );
      }}
    />
  );
}

ListView.propTypes = {
  listOfTools: PropTypes.array.isRequired,
  handleEdit: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  handleShare: PropTypes.func,
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  centered: PropTypes.bool,
  isClickable: PropTypes.bool,
  showOwner: PropTypes.bool,
  type: PropTypes.string,
};

export { ListView };
