import { debounce } from "lodash";
import { ArrowLeft, Pencil } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Input } from "@/components/ui/shims/antd-inputs";
import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { Segmented } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";

import "./ToolNavBar.css";

function ToolNavBar({
  title,
  titleAdornment,
  subtitle,
  onEditTitle,
  editTitleDisabled = false,
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
  searchPlaceholder = "Search by name",
}) {
  const navigate = useNavigate();

  /*
   * Built inline, `debounce(...)` was a fresh instance on every render, so each
   * keystroke started a new 600ms timer on a new closure and nothing was ever
   * coalesced — the search ran per keypress. Memoised with no deps it is
   * created once; the ref is what keeps that single instance calling the
   * CURRENT onSearch/setSearchList props rather than the ones from mount.
   */
  const searchRef = useRef({ onSearch, setSearchList });
  useEffect(() => {
    searchRef.current = { onSearch, setSearchList };
  });
  const onSearchDebounce = useMemo(
    () =>
      debounce((value) => {
        searchRef.current.onSearch?.(value, searchRef.current.setSearchList);
      }, 600),
    [],
  );
  // A pending timer firing after unmount would setState on a dead component.
  useEffect(() => () => onSearchDebounce.cancel(), [onSearchDebounce]);

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
            icon={<ArrowLeft />}
            data-testid="tool-nav-bar-back-btn"
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
                  <Tooltip
                    title={
                      editTitleDisabled
                        ? "Only the owner can change this"
                        : undefined
                    }
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<Pencil />}
                      className="tool-nav-bar__edit-icon"
                      onClick={onEditTitle}
                      disabled={editTitleDisabled}
                      aria-label="Edit title"
                    />
                  </Tooltip>
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
            data-testid="tool-nav-bar-segment"
            className="tool-nav-bar__segment"
          />
        )}
      </div>
      <div className="tool-nav-bar__right">
        {enableSearch && (
          <Input.Search
            key={searchKey}
            className="tool-nav-bar__search"
            placeholder={searchPlaceholder}
            data-testid="tool-nav-bar-search"
            onChange={(event) => onSearchDebounce(event.target.value)}
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
  editTitleDisabled: PropTypes.bool,
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
  searchPlaceholder: PropTypes.string,
};

export { ToolNavBar };
