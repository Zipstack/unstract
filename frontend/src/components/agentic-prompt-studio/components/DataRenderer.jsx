import PropTypes from "prop-types";
import { Table } from "antd";
import "./DataRenderer.css";

const DataRenderer = ({
  data,
  hideEmpty = false,
  highlightData,
  onFieldClick,
  selectedPath,
}) => {
  if (!data || typeof data !== "object") {
    return (
      <div style={{ padding: "16px", color: "#999" }}>No data to display</div>
    );
  }

  return (
    <div style={{ width: "100%" }}>
      {renderValue(
        data,
        "",
        0,
        hideEmpty,
        [],
        highlightData,
        onFieldClick,
        selectedPath
      )}
    </div>
  );
};

const isDirectValue = (value) => {
  return (
    value === null ||
    value === undefined ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
};

const isArrayOfObjects = (value) => {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (item) =>
        typeof item === "object" && item !== null && !Array.isArray(item)
    )
  );
};

const isEmpty = (value) => {
  if (value === null || value === undefined) return true;
  if (typeof value === "string" && value.trim() === "") return true;
  if (Array.isArray(value) && value.length === 0) return true;
  if (
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length === 0
  )
    return true;
  return false;
};

const formatValue = (value) => {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
};

const humanizeKey = (key) => {
  return key
    .replace(/[_-]/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const arraysEqual = (arr1, arr2) => {
  if (!arr1 || !arr2) return false;
  if (arr1.length !== arr2.length) return false;
  return arr1.every((val, index) => val === arr2[index]);
};

const extractHighlightsByFieldPath = (highlightData, path) => {
  if (!highlightData || !path) return [];
  const pathStr = path.join(".");
  return highlightData[pathStr] || [];
};

const renderValue = (
  value,
  key,
  level = 0,
  hideEmpty = false,
  currentPath = [],
  highlightData,
  onFieldClick,
  selectedPath
) => {
  // Skip empty values if hideEmpty is enabled
  if (hideEmpty && isEmpty(value)) {
    return null;
  }

  // Calculate full path for this field
  const fullPath = key ? [...currentPath, key] : currentPath;

  // Check if this field has highlights
  const hasHighlights =
    highlightData &&
    extractHighlightsByFieldPath(highlightData, fullPath).length > 0;

  // Check if this field is selected
  const isSelected = selectedPath && arraysEqual(selectedPath, fullPath);

  // Build className for clickable/selected items
  const getClassName = (baseClass) => {
    let className = baseClass;
    if (hasHighlights) className += " data-renderer-clickable";
    if (isSelected) className += " data-renderer-selected";
    return className;
  };

  const handleClick = () => {
    if (hasHighlights && onFieldClick) {
      onFieldClick(fullPath, value);
    }
  };

  // Rule 1: Direct values → render as key-value rows
  if (isDirectValue(value)) {
    return (
      <div
        key={key}
        className={getClassName("data-renderer-row")}
        onClick={handleClick}
        role={hasHighlights ? "button" : undefined}
        tabIndex={hasHighlights ? 0 : undefined}
      >
        <div className="data-renderer-label">{humanizeKey(key)}</div>
        <div className="data-renderer-value">{formatValue(value)}</div>
      </div>
    );
  }

  // Rule 3: Arrays of objects → render as table
  if (isArrayOfObjects(value)) {
    const items = value;
    const allKeys = Array.from(
      new Set(items.flatMap((item) => Object.keys(item)))
    );

    // Filter out columns where all values are empty (when hideEmpty is enabled)
    const visibleKeys = hideEmpty
      ? allKeys.filter((columnKey) => {
          return items.some((item) => !isEmpty(item[columnKey]));
        })
      : allKeys;

    // If all columns were filtered out, return null
    if (visibleKeys.length === 0 && hideEmpty) {
      return null;
    }

    // Build Ant Design Table columns
    const columns = visibleKeys.map((columnKey) => ({
      title: humanizeKey(columnKey),
      dataIndex: columnKey,
      key: columnKey,
      render: (text, record, index) => {
        const rowPath = [...fullPath, String(index)];
        const cellPath = [...rowPath, columnKey];
        const cellHasHighlights =
          highlightData &&
          extractHighlightsByFieldPath(highlightData, cellPath).length > 0;
        const cellIsSelected =
          selectedPath && arraysEqual(selectedPath, cellPath);

        const cellClassName = cellHasHighlights
          ? cellIsSelected
            ? "data-renderer-cell-selected"
            : "data-renderer-cell-clickable"
          : "";

        const handleCellClick = () => {
          if (cellHasHighlights && onFieldClick) {
            onFieldClick(cellPath, record[columnKey]);
          }
        };

        return (
          <div
            className={cellClassName}
            onClick={handleCellClick}
            role={cellHasHighlights ? "button" : undefined}
            tabIndex={cellHasHighlights ? 0 : undefined}
          >
            {formatValue(text)}
          </div>
        );
      },
    }));

    // Add row keys
    const dataSource = items.map((item, index) => ({
      ...item,
      key: index,
    }));

    return (
      <div key={key} className="data-renderer-section">
        {key && (
          <div
            className={getClassName("data-renderer-section-header")}
            onClick={handleClick}
            role={hasHighlights ? "button" : undefined}
            tabIndex={hasHighlights ? 0 : undefined}
          >
            {humanizeKey(key)}
          </div>
        )}
        <div style={{ padding: "0 16px" }}>
          <Table
            columns={columns}
            dataSource={dataSource}
            pagination={false}
            size="small"
            bordered
          />
        </div>
      </div>
    );
  }

  // Handle arrays of direct values (simple list)
  if (Array.isArray(value)) {
    return (
      <div key={key} className="data-renderer-section">
        {key && (
          <div
            className={getClassName("data-renderer-section-header")}
            onClick={handleClick}
            role={hasHighlights ? "button" : undefined}
            tabIndex={hasHighlights ? 0 : undefined}
          >
            {humanizeKey(key)}
          </div>
        )}
        <div style={{ padding: "0 16px" }}>
          {value.map((item, index) => {
            const itemPath = [...fullPath, String(index)];
            const itemHasHighlights =
              highlightData &&
              extractHighlightsByFieldPath(highlightData, itemPath).length > 0;
            const itemIsSelected =
              selectedPath && arraysEqual(selectedPath, itemPath);

            const handleItemClick = () => {
              if (itemHasHighlights && onFieldClick) {
                onFieldClick(itemPath, item);
              }
            };

            let itemClassName = "data-renderer-array-item";
            if (itemHasHighlights) itemClassName += " data-renderer-clickable";
            if (itemIsSelected) itemClassName += " data-renderer-selected";

            return (
              <div
                key={index}
                className={itemClassName}
                onClick={handleItemClick}
                role={itemHasHighlights ? "button" : undefined}
                tabIndex={itemHasHighlights ? 0 : undefined}
              >
                {isDirectValue(item) ? formatValue(item) : JSON.stringify(item)}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Rule 2: Nested dictionaries → render as section with nested rows
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value);

    // Filter out empty entries if hideEmpty is enabled
    const filteredEntries = hideEmpty
      ? entries.filter(([, v]) => !isEmpty(v))
      : entries;

    // If all entries were filtered out, return null
    if (filteredEntries.length === 0 && hideEmpty) {
      return null;
    }

    // Check if all values are direct (flat object)
    const allDirect = filteredEntries.every(([, v]) => isDirectValue(v));

    if (allDirect && key) {
      // Flat dictionary: render as nested rows
      return (
        <div key={key} className="data-renderer-section">
          <div
            className={getClassName("data-renderer-section-header-bordered")}
            onClick={handleClick}
            role={hasHighlights ? "button" : undefined}
            tabIndex={hasHighlights ? 0 : undefined}
          >
            {humanizeKey(key)}
          </div>
          <div style={{ paddingLeft: "16px" }}>
            {filteredEntries.map(([childKey, childValue]) => {
              const childPath = [...fullPath, childKey];
              const childHasHighlights =
                highlightData &&
                extractHighlightsByFieldPath(highlightData, childPath).length >
                  0;
              const childIsSelected =
                selectedPath && arraysEqual(selectedPath, childPath);

              const handleChildClick = () => {
                if (childHasHighlights && onFieldClick) {
                  onFieldClick(childPath, childValue);
                }
              };

              let childClassName = "data-renderer-row";
              if (childHasHighlights)
                childClassName += " data-renderer-clickable";
              if (childIsSelected) childClassName += " data-renderer-selected";

              return (
                <div
                  key={childKey}
                  className={childClassName}
                  onClick={handleChildClick}
                  role={childHasHighlights ? "button" : undefined}
                  tabIndex={childHasHighlights ? 0 : undefined}
                >
                  <div className="data-renderer-label">
                    {humanizeKey(childKey)}
                  </div>
                  <div className="data-renderer-value">
                    {formatValue(childValue)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      );
    }

    // Complex nested object: render recursively
    const renderedChildren = filteredEntries
      .map(([childKey, childValue]) =>
        renderValue(
          childValue,
          childKey,
          level + 1,
          hideEmpty,
          fullPath,
          highlightData,
          onFieldClick,
          selectedPath
        )
      )
      .filter((child) => child !== null);

    // If all children were filtered out, return null
    if (renderedChildren.length === 0 && hideEmpty) {
      return null;
    }

    return (
      <div key={key} className="data-renderer-section">
        {key && (
          <div
            className={getClassName("data-renderer-section-header-bordered")}
            onClick={handleClick}
            role={hasHighlights ? "button" : undefined}
            tabIndex={hasHighlights ? 0 : undefined}
          >
            {humanizeKey(key)}
          </div>
        )}
        <div style={{ paddingLeft: key ? "16px" : "0" }}>
          {renderedChildren}
        </div>
      </div>
    );
  }

  // Fallback for any other types
  return (
    <div
      key={key}
      className={getClassName("data-renderer-row")}
      onClick={handleClick}
      role={hasHighlights ? "button" : undefined}
      tabIndex={hasHighlights ? 0 : undefined}
    >
      <span style={{ fontWeight: 500 }}>{humanizeKey(key)}:</span>{" "}
      {JSON.stringify(value)}
    </div>
  );
};

DataRenderer.propTypes = {
  data: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  hideEmpty: PropTypes.bool,
  highlightData: PropTypes.object,
  onFieldClick: PropTypes.func,
  selectedPath: PropTypes.array,
};

export default DataRenderer;
