import { DownOutlined, UpOutlined } from "@ant-design/icons";
import { Button, Card, Flex, Space, Tooltip, Typography } from "antd";
import PropTypes from "prop-types";
import { memo, useCallback, useEffect, useRef, useState } from "react";

/**
 * Individual card item renderer for CardGridView
 *
 * @param {Object} props - Component props
 * @param {Object} props.item - Data item to render
 * @param {Object} props.config - Card configuration
 * @param {Function} props.onClick - Click handler for the card
 * @param {boolean} props.listMode - Whether to render in list mode
 * @param {boolean} props.forceExpanded - Force card to stay expanded (e.g., when modal is open)
 * @param {boolean} props.scrollIntoView - Scroll to this card (without forcing expansion)
 * @return {JSX.Element} The rendered card item
 */
function CardItem({
  item,
  config,
  onClick,
  listMode = false,
  forceExpanded = false,
  scrollIntoView = false,
}) {
  const [expanded, setExpanded] = useState(false);
  const cardRef = useRef(null);

  // Auto-scroll to center when card is expanded OR scrollIntoView is requested
  const isExpanded = expanded || forceExpanded;
  const shouldScroll = isExpanded || scrollIntoView;
  useEffect(() => {
    let timerId;
    if (shouldScroll && cardRef.current) {
      timerId = setTimeout(() => {
        cardRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
          inline: "nearest",
        });
      }, 50);
    }
    return () => clearTimeout(timerId);
  }, [shouldScroll]);

  const handleCardClick = useCallback(
    (e) => {
      // Don't trigger card click if clicking on an interactive element
      if (
        e.target.closest("button") ||
        e.target.closest(".ant-switch") ||
        e.target.closest(".ant-dropdown-trigger") ||
        e.target.closest("a") ||
        e.target.closest(".status-badge-clickable") ||
        e.target.closest(".action-icon-btn") ||
        e.target.closest(".ant-popover")
      ) {
        return;
      }

      if (onClick) {
        onClick(item);
      }

      // Toggle on card click (both grid and list mode)
      if (config.expandable) {
        setExpanded((prev) => !prev);
      }
    },
    [item, config.expandable, onClick],
  );

  // Toggle handler for chevron expansion
  const handleToggleExpand = useCallback(
    (e) => {
      e.stopPropagation();
      if (config.expandable) {
        setExpanded((prev) => !prev);
      }
    },
    [config.expandable],
  );

  // Resolve value from config - handles both string keys and functions
  const resolveValue = (valueOrFn, defaultValue = "") => {
    if (typeof valueOrFn === "function") {
      return valueOrFn(item);
    }
    if (typeof valueOrFn === "string") {
      return item[valueOrFn] ?? defaultValue;
    }
    return valueOrFn ?? defaultValue;
  };

  // Check if field should be visible
  const isFieldVisible = (field) => {
    if (field.visible === undefined) {
      return true;
    }
    if (typeof field.visible === "function") {
      return field.visible(item);
    }
    return field.visible;
  };

  // Render a single field
  const renderField = (field) => {
    if (!isFieldVisible(field)) {
      return null;
    }

    const value = item[field.key];

    // Custom renderer takes priority
    if (field.render) {
      return (
        <div key={field.key} className={`card-field ${field.className || ""}`}>
          {field.icon && <span className="card-field-icon">{field.icon}</span>}
          <div className="card-field-content">{field.render(value, item)}</div>
        </div>
      );
    }

    // Default field rendering
    return (
      <div key={field.key} className={`card-field ${field.className || ""}`}>
        {field.icon && <span className="card-field-icon">{field.icon}</span>}
        <div className="card-field-content">
          {field.label && <div className="card-field-label">{field.label}</div>}
          <div className="card-field-value">{value ?? "-"}</div>
        </div>
      </div>
    );
  };

  // Render a section
  const renderSection = (section, index) => {
    const visibleFields = section.fields.filter(isFieldVisible);
    if (visibleFields.length === 0) {
      return null;
    }

    const layoutClass = `card-section-${section.layout || "horizontal"}`;

    return (
      <div
        key={index}
        className={`card-section ${layoutClass} ${section.className || ""}`}
      >
        {visibleFields.map(renderField)}
      </div>
    );
  };

  // Render card header actions
  const renderActions = () => {
    if (!config.header?.actions?.length) {
      return null;
    }

    return (
      <Space size={8} className="card-item-actions">
        {config.header.actions.map((action) => {
          if (action.visible !== undefined) {
            const isVisible =
              typeof action.visible === "function"
                ? action.visible(item)
                : action.visible;
            if (!isVisible) {
              return null;
            }
          }

          // Custom render for action
          if (action.render) {
            return (
              <span
                key={action.key}
                className="card-action-wrapper"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
              >
                {action.render(item)}
              </span>
            );
          }

          return null;
        })}
      </Space>
    );
  };

  // Get card title
  const title = resolveValue(config.header?.title, "Untitled");
  const subtitle = config.header?.subtitle
    ? resolveValue(config.header.subtitle)
    : null;

  // Render chevron toggle for list mode
  const renderExpandChevron = () => {
    if (!config.expandable || !config.expandedContent) {
      return null;
    }

    return (
      <Button
        type="text"
        className="card-expand-chevron"
        icon={isExpanded ? <UpOutlined /> : <DownOutlined />}
        onClick={handleToggleExpand}
      />
    );
  };

  // List mode rendering
  if (listMode && config.listContent) {
    // Non-expandable list mode - no expand/collapse behavior
    if (!config.expandable) {
      return (
        <Card
          ref={cardRef}
          className="card-grid-item card-list-mode"
          hoverable={!!onClick}
          onClick={handleCardClick}
        >
          {/* Custom list content - all content visible, no expanded section */}
          {config.listContent(item, {
            renderActions,
          })}
        </Card>
      );
    }

    // Expandable list mode - original behavior
    return (
      <Card
        ref={cardRef}
        className="card-grid-item card-list-mode"
        hoverable={!!onClick}
        onClick={handleCardClick}
      >
        {/* Custom list content */}
        {config.listContent(item, {
          expanded: isExpanded,
          renderActions,
          renderExpandChevron,
        })}

        {/* Expanded Content - always rendered, visibility controlled by CSS */}
        {config.expandedContent && (
          <div className={`card-list-expanded ${isExpanded ? "expanded" : ""}`}>
            {config.expandedContent(item)}
          </div>
        )}
      </Card>
    );
  }

  return (
    <Card
      ref={cardRef}
      className="card-grid-item"
      hoverable={!!onClick || config.expandable}
      onClick={handleCardClick}
    >
      {/* Card Header */}
      <Flex
        justify="space-between"
        align="flex-start"
        gap={12}
        className="card-item-header"
      >
        <Flex vertical className="card-item-title-section">
          <Tooltip title={title}>
            <Typography.Text className="card-item-title" strong>
              {title}
            </Typography.Text>
          </Tooltip>
          {subtitle && (
            <Typography.Text type="secondary" className="card-item-subtitle">
              {subtitle}
            </Typography.Text>
          )}
        </Flex>
        {renderActions()}
      </Flex>

      {/* Card Sections */}
      {config.sections?.map(renderSection)}

      {/* Expanded Content */}
      {isExpanded && config.expandedContent && (
        <div className="card-expanded-content">
          {config.expandedContent(item)}
        </div>
      )}
    </Card>
  );
}

CardItem.propTypes = {
  item: PropTypes.object.isRequired,
  config: PropTypes.shape({
    header: PropTypes.shape({
      title: PropTypes.oneOfType([PropTypes.string, PropTypes.func]).isRequired,
      subtitle: PropTypes.oneOfType([PropTypes.string, PropTypes.func]),
      actions: PropTypes.arrayOf(
        PropTypes.shape({
          key: PropTypes.string.isRequired,
          render: PropTypes.func,
          visible: PropTypes.oneOfType([PropTypes.bool, PropTypes.func]),
        }),
      ),
    }).isRequired,
    sections: PropTypes.arrayOf(
      PropTypes.shape({
        type: PropTypes.oneOf(["metadata", "stats", "status", "custom"]),
        fields: PropTypes.arrayOf(
          PropTypes.shape({
            key: PropTypes.string.isRequired,
            label: PropTypes.string,
            render: PropTypes.func,
            icon: PropTypes.node,
            visible: PropTypes.oneOfType([PropTypes.bool, PropTypes.func]),
            className: PropTypes.string,
          }),
        ).isRequired,
        layout: PropTypes.oneOf(["horizontal", "vertical", "grid"]),
        className: PropTypes.string,
      }),
    ),
    expandable: PropTypes.bool,
    expandedContent: PropTypes.func,
    listContent: PropTypes.func,
  }).isRequired,
  onClick: PropTypes.func,
  listMode: PropTypes.bool,
  forceExpanded: PropTypes.bool,
  scrollIntoView: PropTypes.bool,
};

// Wrap with memo to prevent unnecessary re-renders when parent array reference changes
const MemoizedCardItem = memo(CardItem);
export { MemoizedCardItem as CardItem };
