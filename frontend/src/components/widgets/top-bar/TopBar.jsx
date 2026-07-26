import debounce from "lodash/debounce";
import { ArrowLeft } from "lucide-react";
import PropTypes from "prop-types";
import { Input } from "@/components/ui/antd-inputs";
import { Col, Row } from "@/components/ui/antd-layout";
import { Typography } from "@/components/ui/antd-typography";
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
        <ArrowLeft onClick={() => navigate(-1)} />
        <Typography className="topbar-title">{title}</Typography>
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
