import debounce from "lodash/debounce";
import { Search } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/shims/antd-inputs";
import { List, Segmented } from "@/components/ui/shims/antd-structure";

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

  /*
   * Built inline, `debounce(...)` was a fresh instance on every render, so each
   * keystroke started a new 300ms timer on a new closure and the list filtered
   * per keypress. `setSearchText` is a stable setState setter, so no deps are
   * needed and the single memoised instance can never go stale.
   */
  const handleInputChange = useMemo(
    () => debounce((value) => setSearchText(value), 300),
    [],
  );
  // A pending timer firing after unmount would setState on a dead component.
  useEffect(() => () => handleInputChange.cancel(), [handleInputChange]);

  const renderModeFilters = () => {
    if (!isConnector || connectorMode) {
      return null;
    }

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
            prefix={<Search className="search-outlined" />}
            onChange={(event) => handleInputChange(event.target.value)}
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
  type: PropTypes.string,
  isConnector: PropTypes.bool,
  connectorMode: PropTypes.string,
};

export { ListOfSources };
