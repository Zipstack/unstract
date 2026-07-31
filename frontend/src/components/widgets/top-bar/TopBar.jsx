import debounce from "lodash/debounce";
import { ArrowLeft } from "lucide-react";
import PropTypes from "prop-types";
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
  const onSearchDebounce = debounce(({ target: { value } }) => {
    onSearch(value);
  }, 600);

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
              onChange={onSearchDebounce}
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
