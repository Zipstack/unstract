import { Col, Empty, Pagination, Row } from "antd";
import PropTypes from "prop-types";

import { CardItem } from "./CardItem.jsx";
import { LoadingSkeleton } from "./LoadingSkeleton.jsx";
import "./CardGridView.css";

/**
 * A reusable card-based grid layout component for entity listings
 *
 * @param {Object} props - Component props
 * @param {Array} props.data - Array of data items to display
 * @param {Object} props.cardConfig - Configuration object for card rendering
 * @param {Function} props.onCardClick - Click handler for card interactions
 * @param {boolean} props.loading - Loading state indicator
 * @param {React.ReactNode} props.emptyState - Custom empty state component
 * @param {Object} props.gridConfig - Responsive grid layout configuration
 * @param {string} props.className - Additional CSS class name
 * @param {Function} props.rowKey - Function to get unique key for each item
 * @param {boolean} props.listMode - When true, renders cards as full-width list items
 * @param {string} props.forceExpandedId - ID of item to keep expanded (e.g., when modal is open)
 * @param {string} props.scrollToId - ID of item to scroll to (without forcing expansion)
 * @return {JSX.Element} The rendered card grid component
 *
 * @example
 * <CardGridView
 *   data={pipelines}
 *   cardConfig={pipelineCardConfig}
 *   loading={isLoading}
 *   onCardClick={(item) => navigate(`/pipeline/${item.id}`)}
 * />
 */
function CardGridView({
  data,
  cardConfig,
  onCardClick,
  loading = false,
  emptyState,
  gridConfig,
  className = "",
  rowKey,
  listMode = false,
  forceExpandedId = null,
  scrollToId = null,
  pagination = null,
}) {
  // Default grid configuration
  const defaultGridConfig = {
    gutter: [16, 16],
    columns: {
      xs: 24, // 1 column on mobile
      sm: 24, // 1 column on small tablets
      md: 12, // 2 columns on tablets
      lg: 12, // 2 columns on small desktops
      xl: 8, // 3 columns on desktops
      xxl: 8, // 3 columns on large screens
    },
  };

  // List mode forces single column layout
  const listModeColumns = {
    xs: 24,
    sm: 24,
    md: 24,
    lg: 24,
    xl: 24,
    xxl: 24,
  };

  const finalGridConfig = {
    gutter: listMode ? [16, 8] : gridConfig?.gutter || defaultGridConfig.gutter,
    columns: listMode
      ? listModeColumns
      : { ...defaultGridConfig.columns, ...gridConfig?.columns },
  };

  // Get unique key for each item
  const getRowKey = (item, index) => {
    if (rowKey) {
      return typeof rowKey === "function" ? rowKey(item) : item[rowKey];
    }
    return item.id || item.key || index;
  };

  // Render loading state
  if (loading) {
    return (
      <div className={`card-grid-view ${className}`}>
        <LoadingSkeleton gridConfig={finalGridConfig} count={6} />
      </div>
    );
  }

  // Render empty state
  if (!data || data.length === 0) {
    return (
      <div className={`card-grid-view card-grid-empty ${className}`}>
        {emptyState || <Empty description="No items found" />}
      </div>
    );
  }

  const { columns, gutter } = finalGridConfig;

  const showPagination = pagination && pagination.total > pagination.pageSize;

  return (
    <div className={`card-grid-view ${className}`}>
      <Row gutter={gutter} className="card-grid-row">
        {data.map((item, index) => (
          <Col
            key={getRowKey(item, index)}
            xs={columns.xs}
            sm={columns.sm}
            md={columns.md}
            lg={columns.lg}
            xl={columns.xl}
            xxl={columns.xxl}
          >
            <CardItem
              item={item}
              config={cardConfig}
              onClick={onCardClick}
              listMode={listMode}
              forceExpanded={
                forceExpandedId && String(forceExpandedId) === String(item.id)
              }
              scrollIntoView={
                scrollToId && String(scrollToId) === String(item.id)
              }
            />
          </Col>
        ))}
      </Row>

      {showPagination && (
        <div className="card-grid-pagination">
          <Pagination
            current={pagination.current}
            pageSize={pagination.pageSize}
            total={pagination.total}
            onChange={pagination.onChange}
            showSizeChanger
            pageSizeOptions={["10", "20", "50"]}
            showTotal={(total, range) =>
              `${range[0]}-${range[1]} of ${total} items`
            }
          />
        </div>
      )}
    </div>
  );
}

CardGridView.propTypes = {
  data: PropTypes.array.isRequired,
  cardConfig: PropTypes.shape({
    header: PropTypes.shape({
      title: PropTypes.oneOfType([PropTypes.string, PropTypes.func]).isRequired,
      subtitle: PropTypes.oneOfType([PropTypes.string, PropTypes.func]),
      actions: PropTypes.array,
    }).isRequired,
    sections: PropTypes.arrayOf(
      PropTypes.shape({
        type: PropTypes.oneOf(["metadata", "stats", "status", "custom"]),
        fields: PropTypes.array.isRequired,
        layout: PropTypes.oneOf(["horizontal", "vertical", "grid"]),
        className: PropTypes.string,
      }),
    ),
    expandable: PropTypes.bool,
    expandedContent: PropTypes.func,
    listContent: PropTypes.func,
  }).isRequired,
  onCardClick: PropTypes.func,
  loading: PropTypes.bool,
  emptyState: PropTypes.node,
  gridConfig: PropTypes.shape({
    gutter: PropTypes.arrayOf(PropTypes.number),
    columns: PropTypes.shape({
      xs: PropTypes.number,
      sm: PropTypes.number,
      md: PropTypes.number,
      lg: PropTypes.number,
      xl: PropTypes.number,
      xxl: PropTypes.number,
    }),
  }),
  className: PropTypes.string,
  rowKey: PropTypes.oneOfType([PropTypes.string, PropTypes.func]),
  listMode: PropTypes.bool,
  forceExpandedId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  scrollToId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  pagination: PropTypes.shape({
    current: PropTypes.number,
    pageSize: PropTypes.number,
    total: PropTypes.number,
    onChange: PropTypes.func,
  }),
};

export { CardGridView };
