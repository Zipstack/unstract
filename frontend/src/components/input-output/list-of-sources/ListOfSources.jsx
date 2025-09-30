import { SearchOutlined } from "@ant-design/icons";
import { Input, List, Segmented } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import debounce from "lodash/debounce";

import { DataSourceCard } from "../data-source-card/DataSourceCard";
import "./ListOfSources.css";

function ListOfSources({
  setSelectedSourceId,
  sourcesList,
  type,
  isConnector,
  connectorMode,
}) {
  const [filteredSourcesList, setFilteredSourcesList] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [localModeFilter, setLocalModeFilter] = useState(null);

  // Apply both search and mode filtering
  useEffect(() => {
    let filteredList = [...sourcesList];

    // Apply mode filter if selected
    if (localModeFilter && isConnector && !connectorMode) {
      filteredList = filteredList.filter((source) => {
        return source?.connector_mode === localModeFilter;
      });
    }

    // Apply search filter
    if (searchText) {
      const searchUpperCase = searchText.toUpperCase().trim();
      filteredList = filteredList.filter((source) => {
        const name = source?.name?.toUpperCase();
        return name.includes(searchUpperCase);
      });
    }

    setFilteredSourcesList(filteredList);
  }, [sourcesList, searchText, localModeFilter, isConnector, connectorMode]);

  const handleInputChange = debounce((event) => {
    const { value } = event.target;
    setSearchText(value);
  }, 300);

  const renderModeFilters = () => {
    if (!isConnector || connectorMode) return null;

    return (
      <Segmented
        className="mode-filter-segment"
        options={[
          { label: "All", value: "ALL" },
          { label: "File Systems", value: "FILESYSTEM" },
          { label: "Databases", value: "DATABASE" },
        ]}
        value={localModeFilter || "ALL"}
        onChange={(value) => {
          const newValue = value === "ALL" ? null : value;
          setLocalModeFilter(newValue);
        }}
      />
    );
  };

  return (
    <div className="list-of-srcs">
      <div className="search-and-filters">
        <div className="searchbox">
          <Input
            placeholder="Search"
            prefix={<SearchOutlined className="search-outlined" />}
            onChange={handleInputChange}
          />
        </div>
        {renderModeFilters()}
      </div>
      <div className="list">
        {filteredSourcesList.length === 0 ? (
          <div className="no-sources">
            <p>
              {searchText && localModeFilter
                ? `No sources found matching "${searchText}" in ${
                    localModeFilter === "FILESYSTEM"
                      ? "File Systems"
                      : "Databases"
                  }`
                : searchText
                ? `No sources found matching "${searchText}"`
                : localModeFilter
                ? `No ${
                    localModeFilter === "FILESYSTEM"
                      ? "File System"
                      : "Database"
                  } connectors available`
                : "No sources available"}
            </p>
            {localModeFilter && (
              <p className="filter-hint">
                Try selecting &quot;All&quot; to show all connectors
              </p>
            )}
          </div>
        ) : (
          <List
            grid={{ gutter: 16, column: 4 }}
            dataSource={filteredSourcesList}
            renderItem={(srcDetails) => (
              <List.Item>
                <DataSourceCard
                  srcDetails={srcDetails}
                  setSelectedSourceId={setSelectedSourceId}
                  type={type}
                />
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
}

ListOfSources.propTypes = {
  setSelectedSourceId: PropTypes.func.isRequired,
  sourcesList: PropTypes.array,
  type: PropTypes.string.isRequired,
  isConnector: PropTypes.bool,
  connectorMode: PropTypes.string,
};

export { ListOfSources };
