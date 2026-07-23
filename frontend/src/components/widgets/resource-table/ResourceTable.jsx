import {
  CaretDownOutlined,
  CaretUpOutlined,
  ClearOutlined,
  DeleteOutlined,
  EditOutlined,
  QuestionCircleOutlined,
  ShareAltOutlined,
  SortAscendingOutlined,
  SortDescendingOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Dropdown,
  Popconfirm,
  Space,
  Table,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";

import "./ResourceTable.css";

// Stable, distinct avatar swatch per owner (seeded on email/name) like the design.
const AVATAR_COLORS = [
  "#f56a00",
  "#7265e6",
  "#00a2ae",
  "#d48806",
  "#1677ff",
  "#eb2f96",
  "#52c41a",
  "#722ed1",
];
const colorForSeed = (seed = "") => {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = seed.codePointAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
};

// Sort-menu wording differs for text vs date columns (per the design).
const SORT_OPTIONS = {
  text: [
    { key: "asc", label: "A-Z", icon: <SortAscendingOutlined /> },
    { key: "desc", label: "Z-A", icon: <SortDescendingOutlined /> },
  ],
  date: [
    { key: "asc", label: "Oldest First", icon: <SortAscendingOutlined /> },
    { key: "desc", label: "Newest First", icon: <SortDescendingOutlined /> },
  ],
};

const formatDate = (value) => {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
};

/**
 * Column header with a sort dropdown (A-Z / Z-A / Clear Sort, or Oldest /
 * Newest First for dates). Server-driven — picking an option refetches.
 * @return {JSX.Element} Rendered sortable header
 */
function SortHeader({ label, sortKey, sortType = "text", sort, onSortChange }) {
  const active = sort?.sortBy === sortKey;
  const items = [
    ...SORT_OPTIONS[sortType],
    { type: "divider" },
    { key: "clear", label: "Clear Sort", icon: <ClearOutlined /> },
  ];
  const onClick = ({ key, domEvent }) => {
    domEvent?.stopPropagation();
    if (key === "clear") {
      onSortChange?.("", "asc");
    } else {
      onSortChange?.(sortKey, key);
    }
  };
  return (
    <Dropdown
      trigger={["click"]}
      menu={{ items, onClick, selectedKeys: active ? [sort.order] : [] }}
    >
      <button
        type="button"
        className={`resource-table-th${active ? " active" : ""}`}
      >
        <span>{label}</span>
        <span className="resource-table-sort-icon">
          <CaretUpOutlined />
          <CaretDownOutlined />
        </span>
      </button>
    </Dropdown>
  );
}

SortHeader.propTypes = {
  label: PropTypes.string.isRequired,
  sortKey: PropTypes.string.isRequired,
  sortType: PropTypes.oneOf(["text", "date"]),
  sort: PropTypes.object,
  onSortChange: PropTypes.func,
};

/**
 * Sortable resource list table (Name / Owned By / Created Date / Actions).
 * Sorting, search and pagination are server-driven — the parent owns the fetch.
 * @return {JSX.Element} Rendered table
 */
function ResourceTable({
  dataSource,
  loading,
  pagination,
  sort,
  onPaginationChange,
  onSortChange,
  titleProp,
  descriptionProp,
  iconProp,
  idProp,
  dateProp = "created_at",
  ownerEmailProp = "created_by_email",
  handleEdit,
  handleShare,
  handleDelete,
  handleCoOwner,
  sessionDetails,
  showOwner = true,
  isClickable = true,
  type,
}) {
  const navigate = useNavigate();

  const renderName = (item) => {
    const icon = iconProp ? item?.[iconProp] : null;
    // Adapters/connectors pass image URLs; Prompt Studio passes emoji. Detect an
    // actual URL/data source rather than a length heuristic — compound (ZWJ)
    // emoji exceed 4 UTF-16 units and would otherwise render as a broken <img>.
    const isImage =
      typeof icon === "string" && /^(https?:\/\/|\/|data:image\/)/.test(icon);
    return (
      <div className="resource-table-name">
        {icon &&
          (isImage ? (
            <img src={icon} alt="" className="resource-table-name-img" />
          ) : (
            <span className="resource-table-name-emoji">{icon}</span>
          ))}
        <div className="resource-table-name-text">
          <Typography.Text
            strong
            ellipsis={{ tooltip: item?.[titleProp] }}
            className="resource-table-name-title"
          >
            {item?.[titleProp]}
          </Typography.Text>
          {descriptionProp && item?.[descriptionProp] && (
            <Typography.Text
              type="secondary"
              ellipsis={{ tooltip: item?.[descriptionProp] }}
              className="resource-table-name-desc"
            >
              {item[descriptionProp]}
            </Typography.Text>
          )}
        </div>
      </div>
    );
  };

  const renderOwner = (item) => {
    const email = item?.[ownerEmailProp];
    const isMe = item?.is_owner || (email && email === sessionDetails?.email);
    const name = isMe ? "Me" : email?.split("@")[0] || "Unknown";
    const extra =
      item?.co_owners_count > 1 ? ` +${item.co_owners_count - 1}` : "";
    const initials = (isMe ? email || "Me" : name).slice(0, 2).toUpperCase();

    const cell = (
      <Space size={10} className="resource-table-owner">
        <Avatar
          size={30}
          className="resource-table-owner-avatar"
          style={{ backgroundColor: colorForSeed(email || name) }}
        >
          {initials}
        </Avatar>
        <div className="resource-table-owner-text">
          <Typography.Text
            className="resource-table-owner-name"
            ellipsis={{ tooltip: `${name}${extra}` }}
          >
            {name}
            {extra}
          </Typography.Text>
          {email && email !== name && (
            <Typography.Text
              type="secondary"
              className="resource-table-owner-email"
              ellipsis={{ tooltip: email }}
            >
              {email}
            </Typography.Text>
          )}
        </div>
      </Space>
    );

    if (!handleCoOwner) {
      return cell;
    }
    return (
      <Tooltip title="Manage Co-Owners">
        <button
          type="button"
          className="resource-table-owner-btn"
          onClick={(event) => {
            event.stopPropagation();
            handleCoOwner(event, item);
          }}
        >
          {cell}
        </button>
      </Tooltip>
    );
  };

  const renderActions = (item) => {
    const deprecated = item?.is_deprecated;
    const disabledTitle = deprecated ? "This adapter is deprecated" : "";
    return (
      <Space
        size={18}
        className="resource-table-actions"
        onClick={(event) => event.stopPropagation()}
        role="none"
      >
        <Tooltip title={disabledTitle}>
          <EditOutlined
            className={`action-icon-buttons edit-icon ${
              deprecated ? "disabled-icon" : ""
            }`}
            onClick={(event) => !deprecated && handleEdit?.(event, item)}
          />
        </Tooltip>
        {handleShare && (
          <Tooltip title={disabledTitle}>
            <ShareAltOutlined
              className={`action-icon-buttons share-icon ${
                deprecated ? "disabled-icon" : ""
              }`}
              onClick={(event) => !deprecated && handleShare(event, item, true)}
            />
          </Tooltip>
        )}
        <Popconfirm
          title={`Delete the ${type}`}
          description={`Are you sure to delete ${item?.[titleProp]}`}
          okText="Yes"
          cancelText="No"
          icon={<QuestionCircleOutlined />}
          onConfirm={(event) => handleDelete?.(event, item)}
        >
          <DeleteOutlined className="action-icon-buttons delete-icon" />
        </Popconfirm>
      </Space>
    );
  };

  const columns = [
    {
      title: (
        <SortHeader
          label="Name"
          sortKey="name"
          sortType="text"
          sort={sort}
          onSortChange={onSortChange}
        />
      ),
      key: "name",
      width: "40%",
      render: (_, item) => renderName(item),
    },
    showOwner && {
      title: (
        <SortHeader
          label="Owned By"
          sortKey="owner"
          sortType="text"
          sort={sort}
          onSortChange={onSortChange}
        />
      ),
      key: "owner",
      width: "26%",
      render: (_, item) => renderOwner(item),
    },
    {
      title: (
        <SortHeader
          label="Created Date"
          sortKey="created"
          sortType="date"
          sort={sort}
          onSortChange={onSortChange}
        />
      ),
      key: "created",
      width: "19%",
      render: (_, item) => formatDate(item?.[dateProp]),
    },
    {
      title: <span className="resource-table-th static right">Actions</span>,
      key: "actions",
      width: "15%",
      align: "right",
      render: (_, item) => renderActions(item),
    },
  ].filter(Boolean);

  // Sorting is handled by the header dropdowns, so onChange only carries the
  // pager here.
  const handleChange = (paginationConf) => {
    onPaginationChange?.(paginationConf.current, paginationConf.pageSize);
  };

  return (
    <Table
      className="resource-table"
      rowKey={idProp}
      tableLayout="fixed"
      columns={columns}
      dataSource={dataSource}
      loading={loading}
      onChange={handleChange}
      rowClassName={isClickable ? "resource-table-row-clickable" : ""}
      onRow={(item) => ({
        onClick: isClickable ? () => navigate(`${item?.[idProp]}`) : undefined,
      })}
      pagination={{
        current: pagination?.current,
        pageSize: pagination?.pageSize,
        total: pagination?.total,
        showSizeChanger: false,
        showTotal: (total) =>
          `Page ${pagination?.current} of ${Math.max(
            1,
            Math.ceil(total / (pagination?.pageSize || 1)),
          )} · ${total} items`,
      }}
    />
  );
}

ResourceTable.propTypes = {
  dataSource: PropTypes.array,
  loading: PropTypes.bool,
  pagination: PropTypes.object,
  sort: PropTypes.object,
  onPaginationChange: PropTypes.func,
  onSortChange: PropTypes.func,
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  dateProp: PropTypes.string,
  ownerEmailProp: PropTypes.string,
  handleEdit: PropTypes.func,
  handleShare: PropTypes.func,
  handleDelete: PropTypes.func,
  handleCoOwner: PropTypes.func,
  sessionDetails: PropTypes.object,
  showOwner: PropTypes.bool,
  isClickable: PropTypes.bool,
  type: PropTypes.string,
};

export { ResourceTable };
