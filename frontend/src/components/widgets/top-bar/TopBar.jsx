import { ArrowLeftOutlined } from "@ant-design/icons";
import { Col, Input, Row, Typography } from "antd";
import PropTypes from "prop-types";
import debounce from "lodash/debounce";
import "./TopBar.css";
import { useNavigate } from "react-router-dom";

function TopBar({
  title,
  enableSearch,
  searchData,
  setFilteredUserList,
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

    const filteredList = [...searchData].filter((user) => {
      const username = user?.email?.toLowerCase();
      const searchTextLowerCase = searchText.toLowerCase();
      return username.includes(searchTextLowerCase);
    });
    setFilteredUserList(filteredList);
  };
  return (
    <>
      <Row align="middle" justify="space-between" className="search-nav">
        <Col>
          <ArrowLeftOutlined onClick={() => navigate(-1)} />
          <Typography className="topbar-title">{title}</Typography>
        </Col>
        <Col>
          <div className="invite-user-search">
            {enableSearch && (
              <Input placeholder="Search Users" onChange={onSearchDebounce} />
            )}
            {children}
          </div>
        </Col>
      </Row>
    </>
  );
}

TopBar.propTypes = {
  title: PropTypes.string.isRequired,
  enableSearch: PropTypes.bool.isRequired,
  searchData: PropTypes.array,
  setFilteredUserList: PropTypes.func,
  children: PropTypes.element,
};

export { TopBar };
