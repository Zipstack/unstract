import { ArrowLeftOutlined, EditOutlined } from "@ant-design/icons";
import { Button, Segmented, Typography } from "antd";
import Search from "antd/es/input/Search";
import { debounce } from "lodash";
import PropTypes from "prop-types";
import { useNavigate } from "react-router-dom";

import "./ToolNavBar.css";

function ToolNavBar({
  title,
  titleAdornment,
  subtitle,
  onEditTitle,
  enableSearch,
  customButtons,
  setSearchList,
  previousRoute,
  previousRouteState,
  onNavigateBack,
  segmentFilter,
  segmentOptions,
  segmentValue,
  onSearch,
  searchKey,
}) {
  const navigate = useNavigate();
  const onSearchDebounce = debounce(({ target: { value } }) => {
    onSearch(value, setSearchList);
  }, 600);

  const handleBack = () => {
    if (onNavigateBack) {
      onNavigateBack();
    } else if (previousRoute) {
      navigate(previousRoute, { state: previousRouteState });
    }
  };

  return (
    <div className="tool-nav-bar">
      <div className="tool-nav-bar__left">
        {(previousRoute || onNavigateBack) && (
          <Button
            type="text"
            shape="circle"
            icon={<ArrowLeftOutlined />}
            onClick={handleBack}
          />
        )}
        {title && (
          <div className="tool-nav-bar__title-area">
            <div className="tool-nav-bar__title-group">
              <div className="tool-nav-bar__title-row">
                <Typography.Text strong className="tool-nav-bar__title">
                  {title}
                </Typography.Text>
                {titleAdornment}
                {onEditTitle && (
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    className="tool-nav-bar__edit-icon"
                    onClick={onEditTitle}
                    aria-label="Edit title"
                  />
                )}
              </div>
              {subtitle && (
                <Typography.Paragraph
                  type="secondary"
                  ellipsis={{ rows: 1, tooltip: true }}
                  className="tool-nav-bar__subtitle"
                >
                  {subtitle}
                </Typography.Paragraph>
              )}
            </div>
          </div>
        )}
        {segmentFilter && segmentOptions && (
          <Segmented
            options={segmentOptions}
            value={segmentValue}
            onChange={segmentFilter}
            className="tool-nav-bar__segment"
          />
        )}
      </div>
      <div className="tool-nav-bar__right">
        {enableSearch && (
          <Search
            key={searchKey}
            className="tool-nav-bar__search"
            placeholder="Search by name"
            onChange={onSearchDebounce}
            allowClear
          />
        )}
        {customButtons}
      </div>
    </div>
  );
}

ToolNavBar.propTypes = {
  title: PropTypes.string,
  titleAdornment: PropTypes.node,
  subtitle: PropTypes.string,
  onEditTitle: PropTypes.func,
  enableSearch: PropTypes.bool,
  customButtons: PropTypes.node,
  setSearchList: PropTypes.func,
  previousRoute: PropTypes.string,
  previousRouteState: PropTypes.object,
  onNavigateBack: PropTypes.func,
  segmentOptions: PropTypes.array,
  segmentValue: PropTypes.string,
  segmentFilter: PropTypes.func,
  onSearch: PropTypes.func,
  searchKey: PropTypes.string,
};

export { ToolNavBar };
