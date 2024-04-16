import { SearchOutlined } from "@ant-design/icons";
import { Input, List } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { DataSourceCard } from "../data-source-card/DataSourceCard";
import debounce from "lodash/debounce";
import "./ListOfSources.css";

function ListOfSources({ setSelectedSourceId, open, sourcesList }) {
  const [filteredSourcesList, setFilteredSourcesList] = useState([]);
  const [searchText, setSearchText] = useState("");

  useEffect(() => {
    onSearch(searchText);
  }, [sourcesList, searchText]);

  useEffect(() => {
    const filteredList = [...sourcesList].filter((source) => {
      const name = source?.name?.toUpperCase();
      const searchUpperCase = searchText.toUpperCase();
      return name.includes(searchUpperCase);
    });
    setFilteredSourcesList(filteredList);
  }, [sourcesList]);

  const onSearch = debounce((searchText) => {
    const searchUpperCase = searchText?.toUpperCase()?.trim();
    const filteredList = sourcesList?.filter((source) => {
      const name = source?.name?.toUpperCase();
      return name.includes(searchUpperCase);
    });
    setFilteredSourcesList(filteredList);
  }, 600);

  const handleInputChange = (event) => {
    const { value } = event.target;
    setSearchText(value);
    onSearch(value);
  };

  return (
    <div className="list-of-srcs">
      <div className="searchbox">
        <Input
          placeholder="Search"
          prefix={<SearchOutlined className="search-outlined" />}
          onChange={handleInputChange}
          value={searchText}
        />
      </div>
      <div className="list">
        <List
          grid={{ gutter: 16, column: 4 }}
          dataSource={filteredSourcesList}
          renderItem={(srcDetails) => (
            <List.Item>
              <DataSourceCard
                srcDetails={srcDetails}
                setSelectedSourceId={setSelectedSourceId}
              />
            </List.Item>
          )}
        />
      </div>
    </div>
  );
}

ListOfSources.propTypes = {
  setSelectedSourceId: PropTypes.func.isRequired,
  open: PropTypes.bool,
  sourcesList: PropTypes.array,
};

export { ListOfSources };
