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
  QuestionCircleOutlined,
  ShareAltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

function ListView({
  listOfTools,
  handleEdit,
  handleDelete,
  handleShare,
  handleCoOwner,
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
  const handleDeleteClick = (event, tool) => {
    event.stopPropagation(); // Stop propagation to prevent list item click
    handleDelete(event, tool);
  };

  const handleShareClick = (event, tool, isEdit) => {
    event.stopPropagation(); // Stop propagation to prevent list item click
    handleShare(event, tool, isEdit);
  };

  const handleCoOwnerClick = (event, tool) => {
    event.stopPropagation();
    handleCoOwner(event, tool);
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

    return (
      <Flex
        gap={20}
        align="center"
        justify="space-between"
        className="list-view-container"
      >
        <div className="list-view-content">
          <div className="adapters-list-title-container display-flex-left">
            {title}
          </div>
          {showOwner && (
            <Tooltip title={handleCoOwner ? "Manage Co-Owners" : ""}>
              <div
                className={`adapters-list-profile-container${
                  handleCoOwner ? " owner-clickable" : ""
                }`}
                onClick={
                  handleCoOwner
                    ? (event) => handleCoOwnerClick(event, item)
                    : undefined
                }
                role={handleCoOwner ? "button" : undefined}
              >
                <Avatar
                  size={20}
                  className="adapters-list-user-avatar"
                  icon={<UserOutlined />}
                />
                <Typography.Text disabled className="adapters-list-user-prefix">
                  Owned By:
                </Typography.Text>
                <Typography.Text className="shared-username">
                  {(() => {
                    const name = item?.is_owner
                      ? "Me"
                      : item?.created_by_email || "-";
                    const extra =
                      item?.co_owners_count > 1
                        ? ` +${item.co_owners_count - 1}`
                        : "";
                    return `${name}${extra}`;
                  })()}
                </Typography.Text>
              </div>
            </Tooltip>
          )}
        </div>
        <div
          className="action-button-container"
          onClick={(event) => event.stopPropagation()}
          role="none"
        >
          <Tooltip
            title={item?.is_deprecated ? "This adapter is deprecated" : ""}
          >
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
      </Flex>
    );
  };

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
            <List.Item.Meta
              className="list-item-desc"
              title={renderTitle(item)}
              description={
                <Typography.Text type="secondary" ellipsis>
                  <Tooltip title={item[descriptionProp]}>
                    {item[descriptionProp]}
                  </Tooltip>
                </Typography.Text>
              }
            ></List.Item.Meta>
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
  handleCoOwner: PropTypes.func,
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
