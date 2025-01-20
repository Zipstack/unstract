import { Button, Col, Row, Segmented, Typography } from "antd";
import "./ToolNavBar.css";
import Search from "antd/es/input/Search";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { debounce } from "lodash";
import PropTypes from "prop-types";
import { useCallback, useMemo, useEffect } from "react";

function ToolNavBar({
  title,
  enableSearch,
  CustomButtons,
  setSearchList,
  previousRoute,
  segmentFilter,
  segmentOptions,
  onSearch,
}) {
  const navigate = useNavigate();

  const handleBackClick = useCallback(() => {
    if (previousRoute) {
      navigate(previousRoute);
    }
  }, [previousRoute]);

  const onSearchDebounce = useMemo(() => {
    const debouncedFunction = debounce(({ target: { value } }) => {
      if (onSearch) {
        onSearch(value, setSearchList);
      }
    }, 600);
    return debouncedFunction;
  }, [onSearch, setSearchList]);

  // Cleanup debounced function on unmount
  useEffect(() => {
    return () => {
      onSearchDebounce.cancel();
    };
  }, [onSearchDebounce]);

  // Handle segment change
  const handleSegmentChange = useCallback(
    (value) => {
      if (segmentFilter) {
        segmentFilter(value);
      }
    },
    [segmentFilter]
  );

  return (
    <Row align="middle" justify="space-between" className="searchNav">
      <Col>
        {previousRoute && (
          <Button
            type="text"
            shape="circle"
            icon={<ArrowLeftOutlined />}
            onClick={handleBackClick}
          />
        )}
        {title && <Typography className="tool-nav-title">{title}</Typography>}
        {segmentFilter && segmentOptions && (
          <Segmented
            options={segmentOptions}
            onChange={handleSegmentChange}
            className="tool-bar-segment"
          />
        )}
      </Col>
      <Col>
        {enableSearch && (
          <Search
            className="api-search-input"
            placeholder="Search by name"
            onChange={onSearchDebounce}
            allowClear
          />
        )}
        {CustomButtons && <CustomButtons />}
      </Col>
    </Row>
  );
}

ToolNavBar.propTypes = {
  title: PropTypes.string,
  enableSearch: PropTypes.bool,
  CustomButtons: PropTypes.oneOfType([PropTypes.func, PropTypes.elementType]),
  setSearchList: PropTypes.func,
  previousRoute: PropTypes.string,
  segmentOptions: PropTypes.array,
  segmentFilter: PropTypes.func,
  onSearch: PropTypes.func,
};

export { ToolNavBar };
