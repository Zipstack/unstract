// ListView.jsx

import {
  Avatar,
  Image,
  Popconfirm,
  Space,
  Table,
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
import moment from "moment";
import { useMemo, useCallback } from "react";

import { useSessionStore } from "../../../store/session-store";

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
  type,
}) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();

  const handleRowClick = useCallback(
    (record) => {
      if (isClickable) {
        navigate(`${record[idProp]}`);
      }
    },
    [navigate, idProp, isClickable]
  );

  const renderNameColumn = useCallback(
    (text, record) => {
      let titleContent = null;
      if (iconProp && record[iconProp]?.length > 4) {
        titleContent = (
          <Space className="adapter-cover-img" size={10}>
            <Image
              src={record[iconProp]}
              preview={false}
              className="fit-cover"
            />
            <Typography.Text className="adapters-list-title">
              {record[titleProp]}
            </Typography.Text>
          </Space>
        );
      } else if (iconProp) {
        titleContent = (
          <Typography.Text className="adapters-list-title">
            {`${record[iconProp]} ${record[titleProp]}`}
          </Typography.Text>
        );
      } else {
        titleContent = (
          <Typography.Text className="adapters-list-title">
            {record[titleProp]}
          </Typography.Text>
        );
      }
      return (
        <>
          <Typography.Text strong className="display-flex-left">
            {titleContent}
          </Typography.Text>
          <Typography.Text type="secondary" ellipsis>
            <Tooltip title={record?.[descriptionProp]}>
              {record?.[descriptionProp]}
            </Tooltip>
          </Typography.Text>
        </>
      );
    },
    [iconProp, titleProp, descriptionProp]
  );

  const renderOwnedByColumn = useCallback(
    (text) => {
      const owner = text === sessionDetails?.email ? "Me" : text || "-";
      return (
        <div className="adapters-list-profile-container">
          <Avatar
            size={20}
            className="adapters-list-user-avatar"
            icon={<UserOutlined />}
          />
          <Typography.Text disabled className="adapters-list-user-prefix">
            Owned By:
          </Typography.Text>
          <Typography.Text className="shared-username">{owner}</Typography.Text>
        </div>
      );
    },
    [sessionDetails?.email]
  );

  const renderDateColumn = useCallback(
    (text) => (text ? moment(text).format("YYYY-MM-DD HH:mm:ss") : "-"),
    []
  );

  const handleEditClick = useCallback(
    (event, record) => {
      event.stopPropagation();
      handleEdit(event, record);
    },
    [handleEdit]
  );

  const handleShareClick = useCallback(
    (event, record) => {
      event.stopPropagation();
      handleShare?.(record, true);
    },
    [handleShare]
  );

  const handleDeleteClick = useCallback(
    (event, record) => {
      event.stopPropagation();
      handleDelete(event, record);
    },
    [handleDelete]
  );

  const renderActionsColumn = useCallback(
    (text, record) => (
      <div
        className="action-button-container"
        onClick={(event) => event.stopPropagation()}
        role="none"
      >
        <EditOutlined
          key={`${record[idProp]}-edit`}
          onClick={(event) => handleEditClick(event, record)}
          className="action-icon-buttons edit-icon"
        />
        {handleShare && (
          <ShareAltOutlined
            key={`${record[idProp]}-share`}
            className="action-icon-buttons"
            onClick={(event) => handleShareClick(event, record)}
          />
        )}
        <Popconfirm
          key={`${record[idProp]}-delete`}
          title={`Delete the ${type}`}
          description={`Are you sure to delete ${record[titleProp]}?`}
          okText="Yes"
          cancelText="No"
          icon={<QuestionCircleOutlined />}
          onConfirm={(event) => {
            handleDeleteClick(event, record);
          }}
        >
          <Typography.Text>
            <DeleteOutlined className="action-icon-buttons delete-icon" />
          </Typography.Text>
        </Popconfirm>
      </div>
    ),
    [
      idProp,
      titleProp,
      type,
      handleEditClick,
      handleShare,
      handleShareClick,
      handleDeleteClick,
    ]
  );

  const columns = useMemo(
    () => [
      {
        title: "Name",
        dataIndex: titleProp,
        key: "name",
        sorter: (a, b) =>
          a[titleProp]
            ?.toLowerCase()
            .localeCompare(b[titleProp]?.toLowerCase()),
        render: renderNameColumn,
      },
      {
        title: "Owned By",
        dataIndex: "created_by_email",
        key: "ownedBy",
        sorter: (a, b) =>
          (a.created_by_email || "")
            .toLowerCase()
            .localeCompare((b.created_by_email || "").toLowerCase()),
        render: renderOwnedByColumn,
      },
      {
        title: "Created At",
        dataIndex: "created_at",
        key: "createdAt",
        sorter: (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
        render: renderDateColumn,
      },
      {
        title: "Modified At",
        dataIndex: "modified_at",
        key: "modifiedAt",
        sorter: (a, b) =>
          new Date(a.modified_at).getTime() - new Date(b.modified_at).getTime(),
        render: renderDateColumn,
      },
      {
        title: "Actions",
        key: "actions",
        align: "center",
        render: renderActionsColumn,
      },
    ],
    [
      titleProp,
      renderNameColumn,
      renderOwnedByColumn,
      renderDateColumn,
      renderActionsColumn,
    ]
  );

  return (
    <Table
      rowKey={idProp}
      dataSource={listOfTools}
      columns={columns}
      pagination={{
        position: ["bottomRight"],
        size: "small",
      }}
      onRow={(record) => ({
        onClick: () => handleRowClick(record),
        className: `cur-pointer ${centered ? "centered" : ""}`,
      })}
      className="width-100"
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

ListView.defaultProps = {
  handleShare: null,
  descriptionProp: "",
  iconProp: "",
  centered: false,
  isClickable: true,
  showOwner: false,
  type: "",
};

export { ListView };
