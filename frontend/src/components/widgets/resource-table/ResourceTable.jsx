import {
  ArrowDownAZ,
  ArrowUpAZ,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  Eraser,
  Pencil,
  Share2,
  Trash2,
} from "lucide-react";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";
import { Space } from "@/components/ui/shims/antd-layout";
import { Avatar } from "@/components/ui/shims/antd-leaves";
import {
  Dropdown,
  Popconfirm,
  Tooltip,
} from "@/components/ui/shims/antd-overlays";
import { Table } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";

import { formattedDateTime, timeAgo } from "../../../helpers/GetStaticData";
import "./ResourceTable.css";

// Service-account address minted by `create_api_user_for_key`. Its owner is a
// platform API key, not a person, so the cell is labelled rather than named.
const PLATFORM_KEY_EMAIL_DOMAIN = "@platform.internal";

// Stable, distinct avatar swatch per owner (seeded on email/name) like the
// design: a light pastel fill paired with a matching darker initial.
const AVATAR_COLORS = [
  { bg: "#ffccc7", fg: "#f5222d" },
  { bg: "#ffe7ba", fg: "#fa8c16" },
  { bg: "#fff1b8", fg: "#faad14" },
  { bg: "#d9f7be", fg: "#52c41a" },
  { bg: "#b5f5ec", fg: "#13c2c2" },
  { bg: "#bae0ff", fg: "#1677ff" },
  { bg: "#efdbff", fg: "#722ed1" },
  { bg: "#ffd6e7", fg: "#eb2f96" },
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
    { key: "asc", label: "A-Z", icon: <ArrowUpAZ /> },
    { key: "desc", label: "Z-A", icon: <ArrowDownAZ /> },
  ],
  date: [
    { key: "asc", label: "Oldest First", icon: <ArrowUpAZ /> },
    { key: "desc", label: "Newest First", icon: <ArrowDownAZ /> },
  ],
};

/**
 * Column header with a sort dropdown (A-Z / Z-A / Clear Sort, or Oldest /
 * Newest First for dates). Server-driven — picking an option refetches.
 * @return {JSX.Element} Rendered sortable header
 */
function SortHeader({
  label,
  sortKey,
  sortType = "text",
  sort,
  userSorted,
  onSortChange,
  testId,
}) {
  // Don't light up the default sort column on load — only once the user picks.
  const active = userSorted && sort?.sortBy === sortKey;
  const items = [
    ...SORT_OPTIONS[sortType],
    { type: "divider" },
    { key: "clear", label: "Clear Sort", icon: <Eraser /> },
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
    // The menu is portalled and its entries repeat verbatim across the four
    // sortable columns, so `${testId}-menu-item-asc` is the only thing that
    // distinguishes "A-Z under Name" from "A-Z under Modified".
    <Dropdown
      trigger={["click"]}
      menu={{ items, onClick, selectedKeys: active ? [sort.order] : [] }}
      data-testid={testId ? `${testId}-menu` : undefined}
    >
      <button
        type="button"
        data-testid={testId}
        className={`resource-table-th${active ? " active" : ""}`}
      >
        <span>{label}</span>
        <span className="resource-table-sort-icon">
          <ChevronUp />
          <ChevronDown />
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
  userSorted: PropTypes.bool,
  onSortChange: PropTypes.func,
  testId: PropTypes.string,
};

/**
 * Sortable resource list table (Name / Owned By / Created / Modified / Actions).
 * Sorting, search and pagination are server-driven — the parent owns the fetch.
 * @return {JSX.Element} Rendered table
 */
function ResourceTable({
  dataSource,
  loading,
  pagination,
  sort,
  userSorted,
  onPaginationChange,
  onSortChange,
  titleProp,
  descriptionProp,
  iconProp,
  idProp,
  dateProp = "created_at",
  modifiedProp = "modified_at",
  ownerEmailsProp = "owner_emails",
  countProp,
  countLabel,
  extraColumns = [],
  handleEdit,
  handleShare,
  handleDelete,
  handleCoOwner,
  onRowClick,
  sessionDetails,
  showOwner = true,
  isClickable = true,
  type,
  /**
   * Prefix for the `data-testid`s below. Every control in this table repeats
   * once per row — the action buttons share an aria-label (`Edit Prompt
   * Project`), and the rows themselves differ only by content — so a test
   * needs the row id to address one of them. Callers pass a page-specific
   * prefix (`prompt-studio-list`) so the resulting locators read as the screen
   * they belong to rather than as this widget.
   */
  testIdPrefix = "resource-table",
}) {
  const navigate = useNavigate();
  /*
   * Note the shape: the ROW is `<prefix>-row-<id>` and a control inside it is
   * `<prefix>-<action>-<id>` — deliberately NOT `<prefix>-row-<action>-<id>`,
   * which would make every action button a prefix-match for the row itself and
   * leave `[data-testid^="…-row-"]` matching five elements per row.
   */
  const rowTestId = (item, action) =>
    `${testIdPrefix}-${action}-${item?.[idProp]}`;

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
          {countProp && item?.[countProp] != null && (
            <Typography.Text
              type="secondary"
              className="resource-table-name-meta"
            >
              {countLabel}: {item[countProp]}
            </Typography.Text>
          )}
        </div>
      </div>
    );
  };

  const renderOwner = (item) => {
    // owner_emails is earliest-first; [0] is the primary shown owner.
    // Fall back to created_by_email so rows with no live OWNER membership
    // (pre-backfill rows) don't render "Unknown".
    const ownerEmails = item?.[ownerEmailsProp];
    const rawEmail =
      (Array.isArray(ownerEmails) ? ownerEmails[0] : undefined) ??
      item?.created_by_email;
    // Reached only when a platform key's creator has since been deleted, so no
    // human can be named. Suppress the synthetic address rather than dress a
    // machine identity up as a colleague.
    const isPlatformKey = Boolean(
      rawEmail?.endsWith(PLATFORM_KEY_EMAIL_DOMAIN),
    );
    const email = isPlatformKey ? undefined : rawEmail;
    // "Me" must track the DISPLAYED owner, not the viewer's own membership —
    // else a co-owner sees "Me" over the primary owner's avatar/email. Match on
    // the shown email so the creator viewing their own resource still reads "Me".
    const isMe = Boolean(email) && email === sessionDetails?.email;
    let name = email?.split("@")[0] || "Unknown";
    if (isPlatformKey) {
      name = "Platform key";
    } else if (isMe) {
      name = "Me";
    }
    const extra =
      item?.co_owners_count > 1 ? ` +${item.co_owners_count - 1}` : "";
    const initials = (email || name).slice(0, 2).toUpperCase();
    const swatch = colorForSeed(email || name);

    const cell = (
      <Space size={10} className="resource-table-owner">
        <Avatar
          size={30}
          className="resource-table-owner-avatar"
          style={{ backgroundColor: swatch.bg, color: swatch.fg }}
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
      <button
        type="button"
        className="resource-table-owner-btn"
        data-testid={rowTestId(item, "owner")}
        onClick={(event) => {
          event.stopPropagation();
          handleCoOwner(event, item);
        }}
      >
        {cell}
        <span className="resource-table-sr-only">
          Manage co-owners{item?.[titleProp] ? ` for ${item[titleProp]}` : ""}
        </span>
      </button>
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
          <button
            type="button"
            className="action-icon-btn"
            aria-label={`Edit ${type}`}
            data-testid={rowTestId(item, "edit")}
            aria-disabled={deprecated}
            onClick={(event) => !deprecated && handleEdit?.(event, item)}
          >
            <Pencil className="action-icon-buttons edit-icon" />
          </button>
        </Tooltip>
        {handleShare && (
          <Tooltip title={disabledTitle}>
            <button
              type="button"
              className="action-icon-btn"
              aria-label={`Share ${type}`}
              data-testid={rowTestId(item, "share")}
              aria-disabled={deprecated}
              onClick={(event) => !deprecated && handleShare(event, item, true)}
            >
              <Share2 className="action-icon-buttons share-icon" />
            </button>
          </Tooltip>
        )}
        {/*
         * The confirm panel is NOT keyed by row: only one can be open at a
         * time, so a per-row id would just make the locator longer without
         * making it more specific. The button that opens it is per-row,
         * because every row has one.
         */}
        <Popconfirm
          title={`Delete the ${type}`}
          description={`Are you sure to delete ${item?.[titleProp]}`}
          okText="Yes"
          cancelText="No"
          icon={<CircleHelp />}
          data-testid={`${testIdPrefix}-delete-confirm`}
          onConfirm={(event) => handleDelete?.(event, item)}
        >
          <button
            type="button"
            className="action-icon-btn"
            aria-label={`Delete ${type}`}
            data-testid={rowTestId(item, "delete")}
          >
            <Trash2 className="action-icon-buttons delete-icon" />
          </button>
        </Popconfirm>
      </Space>
    );
  };

  const columns = [
    {
      title: (
        <SortHeader
          testId={`${testIdPrefix}-sort-name`}
          label="Name"
          sortKey={titleProp}
          sortType="text"
          sort={sort}
          userSorted={userSorted}
          onSortChange={onSortChange}
        />
      ),
      key: "name",
      width: "34%",
      render: (_, item) => renderName(item),
    },
    showOwner && {
      title: <span className="resource-table-th static">Owned By</span>,
      key: "owner",
      width: "22%",
      render: (_, item) => renderOwner(item),
    },
    {
      title: (
        <SortHeader
          testId={`${testIdPrefix}-sort-created`}
          label="Created"
          sortKey={dateProp}
          sortType="date"
          sort={sort}
          userSorted={userSorted}
          onSortChange={onSortChange}
        />
      ),
      key: "created",
      width: "15%",
      render: (_, item) => formattedDateTime(item?.[dateProp]) || "-",
    },
    {
      title: (
        <SortHeader
          testId={`${testIdPrefix}-sort-modified`}
          label="Modified"
          sortKey={modifiedProp}
          sortType="date"
          sort={sort}
          userSorted={userSorted}
          onSortChange={onSortChange}
        />
      ),
      key: "modified",
      width: "15%",
      render: (_, item) => {
        const iso = item?.[modifiedProp];
        const rel = timeAgo(iso);
        // The <span> is load-bearing: Tooltip renders a Radix trigger with
        // `asChild`, which slots onto a single ELEMENT child. `timeAgo` returns
        // a string, and slotting onto text throws "Primitive.button failed to
        // slot onto its children" — taking down every route that renders this
        // table with at least one row. antd's Tooltip accepted a bare string
        // here, so the shape survived the conversion unnoticed.
        return rel ? (
          <Tooltip title={formattedDateTime(iso)}>
            <span>{rel}</span>
          </Tooltip>
        ) : (
          "-"
        );
      },
    },
    // Resource-specific columns (e.g. Files, Latest Version) sit between the
    // shared date columns and Actions.
    ...extraColumns,
    {
      title: <span className="resource-table-th static right">Actions</span>,
      key: "actions",
      width: "14%",
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
      data-testid={testIdPrefix}
      rowKey={idProp}
      tableLayout="fixed"
      columns={columns}
      dataSource={dataSource}
      loading={loading}
      onChange={handleChange}
      rowClassName={isClickable ? "resource-table-row-clickable" : ""}
      onRow={(item) => ({
        // Whatever `onRow` returns is spread onto the <tr>, which is how the
        // row gets an id at all — there is no other hook for it.
        "data-testid": `${testIdPrefix}-row-${item?.[idProp]}`,
        // onRowClick lets callers override the default relative nav (e.g. an
        // absolute org-scoped path with router state).
        onClick: isClickable
          ? () =>
              onRowClick ? onRowClick(item) : navigate(`${item?.[idProp]}`)
          : undefined,
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
  userSorted: PropTypes.bool,
  onPaginationChange: PropTypes.func,
  onSortChange: PropTypes.func,
  titleProp: PropTypes.string.isRequired,
  descriptionProp: PropTypes.string,
  iconProp: PropTypes.string,
  idProp: PropTypes.string.isRequired,
  dateProp: PropTypes.string,
  modifiedProp: PropTypes.string,
  ownerEmailsProp: PropTypes.string,
  countProp: PropTypes.string,
  countLabel: PropTypes.string,
  extraColumns: PropTypes.array,
  handleEdit: PropTypes.func,
  handleShare: PropTypes.func,
  handleDelete: PropTypes.func,
  handleCoOwner: PropTypes.func,
  onRowClick: PropTypes.func,
  sessionDetails: PropTypes.object,
  showOwner: PropTypes.bool,
  isClickable: PropTypes.bool,
  type: PropTypes.string,
  testIdPrefix: PropTypes.string,
};

export { ResourceTable };
