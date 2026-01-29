import { Button, Col, Row, Segmented, Typography } from "antd";
import "./ToolNavBar.css";
import Search from "antd/es/input/Search";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { debounce } from "lodash";
import PropTypes from "prop-types";

function ToolNavBar({
  title,
  enableSearch,
  CustomButtons,
  setSearchList,
  previousRoute,
  segmentFilter,
  segmentOptions,
  onSearch,
  searchKey,
}) {
  const navigate = useNavigate();
  const onSearchDebounce = debounce(({ target: { value } }) => {
    onSearch(value, setSearchList);
  }, 600);

  return (
    <Row align="middle" justify="space-between" className="searchNav">
      <Col>
        {previousRoute && (
          <Button
            type="text"
            shape="circle"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate(previousRoute)}
          />
        )}
        {title && (
          <Typography
            style={{
              fontWeight: 600,
              fontSize: "16px",
              display: "inline",
              lineHeight: "24px",
            }}
          >
            {title}
          </Typography>
        )}
        {segmentFilter && segmentOptions && (
          <Segmented
            options={segmentOptions}
            onChange={segmentFilter}
            className="tool-bar-segment"
          />
        )}
      </Col>
      <Col>
        {enableSearch && (
          <Search
            key={searchKey}
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
  CustomButtons: PropTypes.func,
  setSearchList: PropTypes.func,
  previousRoute: PropTypes.string,
  segmentOptions: PropTypes.array,
  segmentFilter: PropTypes.func,
  onSearch: PropTypes.func,
  searchKey: PropTypes.string,
};

export { ToolNavBar };
