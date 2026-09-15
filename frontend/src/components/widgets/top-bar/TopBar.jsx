import debounce from "lodash/debounce";
import { ArrowLeft } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useMemo, useRef } from "react";
import { Input } from "@/components/ui/shims/antd-inputs";
import { Col, Row } from "@/components/ui/shims/antd-layout";
import { Typography } from "@/components/ui/shims/antd-typography";
import "./TopBar.css";
import { useNavigate } from "react-router-dom";

function TopBar({
  title,
  enableSearch,
  searchData,
  setFilteredUserList,
  searchKey = "email",
  searchPlaceholder = "Search Users",
  children,
}) {
  const navigate = useNavigate();

  const onSearch = (searchText = "") => {
    if (searchText?.trim() === "") {
      setFilteredUserList(searchData);
      return;
    }

    const searchTextLowerCase = searchText.toLowerCase();
    const filteredList = [...searchData].filter((item) => {
      const value = item?.[searchKey]?.toLowerCase() ?? "";
      return value.includes(searchTextLowerCase);
    });
    setFilteredUserList(filteredList);
  };

  /*
   * Built inline, `debounce(...)` was a fresh instance on every render, so each
   * keystroke started a new 600ms timer on a new closure and nothing was ever
   * coalesced — the filter ran per keypress. Memoised with no deps it is
   * created once; the ref is what keeps that single instance calling the
   * CURRENT onSearch, so it never filters a stale `searchData`.
   */
  const onSearchRef = useRef(onSearch);
  useEffect(() => {
    onSearchRef.current = onSearch;
  });
  const onSearchDebounce = useMemo(
    () => debounce((value) => onSearchRef.current(value), 600),
    [],
  );
  // A pending timer firing after unmount would setState on a dead component.
  useEffect(() => () => onSearchDebounce.cancel(), [onSearchDebounce]);

  return (
    <Row align="middle" justify="space-between" className="search-nav">
      <Col>
        {/*
         * A real <button>, not a bare <ArrowLeft onClick>. lucide renders a
         * plain SVG, so the handler landed on an element with no button
         * semantics — not keyboard reachable, and the click did not register
         * at all on these pages. antd's icon component supplied that wrapper.
         *
         * The row is an explicit flex: `.topbar-title` asks for `display:
         * inline`, but Tailwind's preflight makes the SVG `display: block`,
         * which broke the line and stacked the arrow above the title.
         */}
        <div className="topbar-heading">
          <button
            type="button"
            className="topbar-back"
            aria-label="Go back"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft />
          </button>
          <Typography className="topbar-title">{title}</Typography>
        </div>
      </Col>
      <Col>
        <div className="invite-user-search">
          {enableSearch && (
            <Input
              placeholder={searchPlaceholder}
              data-testid="top-bar-search"
              onChange={(event) => onSearchDebounce(event.target.value)}
            />
          )}
          {children}
        </div>
      </Col>
    </Row>
  );
}

TopBar.propTypes = {
  title: PropTypes.string.isRequired,
  enableSearch: PropTypes.bool.isRequired,
  searchData: PropTypes.array,
  setFilteredUserList: PropTypes.func,
  searchKey: PropTypes.string,
  searchPlaceholder: PropTypes.string,
  children: PropTypes.element,
};

export { TopBar };
