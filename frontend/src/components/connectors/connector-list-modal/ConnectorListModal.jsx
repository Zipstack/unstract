import { SearchOutlined } from "@ant-design/icons";
import { Input, Row, Col, Tabs, Typography, Spin } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import debounce from "lodash/debounce";

import { ConnectorCard } from "../connector-card/ConnectorCard";
import "./ConnectorListModal.css";

function ConnectorListModal({
  connectors,
  onSelectConnector,
  selectedConnectorId,
  loading = false,
}) {
  const [filteredConnectors, setFilteredConnectors] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [activeTab, setActiveTab] = useState("all");

  useEffect(() => {
    filterConnectors(searchText, activeTab);
  }, [connectors, searchText, activeTab]);

  const filterConnectors = debounce((searchText, mode) => {
    let filtered = [...connectors];

    // Filter by search text
    if (searchText?.trim()) {
      const searchUpper = searchText.toUpperCase().trim();
      filtered = filtered.filter((connector) =>
        connector?.name?.toUpperCase().includes(searchUpper)
      );
    }

    // Filter by connector mode
    if (mode !== "all") {
      filtered = filtered.filter((connector) => {
        if (mode === "FILESYSTEM") {
          return (
            connector?.connector_mode === "FILESYSTEM" ||
            connector?.can_write ||
            connector?.can_read
          ); // fallback logic
        }
        if (mode === "DATABASE") {
          return connector?.connector_mode === "DATABASE";
        }
        return true;
      });
    }

    setFilteredConnectors(filtered);
  }, 300);

  const handleSearchChange = (event) => {
    const { value } = event.target;
    setSearchText(value);
  };

  const handleTabChange = (key) => {
    setActiveTab(key);
  };

  const handleConnectorSelect = (connector) => {
    onSelectConnector(connector);
  };

  const tabItems = [
    {
      key: "all",
      label: "All Connectors",
    },
    {
      key: "FILESYSTEM",
      label: "File Systems",
    },
    {
      key: "DATABASE",
      label: "Databases",
    },
  ];

  if (loading) {
    return (
      <div className="connector-list-loading">
        <Spin size="large" />
        <Typography.Text
          style={{ marginTop: 16, display: "block", textAlign: "center" }}
        >
          Loading connectors...
        </Typography.Text>
      </div>
    );
  }

  return (
    <div className="connector-list-modal">
      <div className="connector-search-section">
        <Input
          placeholder="Search for connectors..."
          prefix={<SearchOutlined className="search-icon" />}
          onChange={handleSearchChange}
          value={searchText}
          size="large"
        />
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={tabItems}
        className="connector-tabs"
      />

      <div className="connector-grid-container">
        {filteredConnectors.length === 0 ? (
          <div className="no-connectors">
            <Typography.Text type="secondary">
              {searchText
                ? "No connectors found matching your search."
                : "No connectors available."}
            </Typography.Text>
          </div>
        ) : (
          <Row gutter={[24, 24]} justify="start">
            {filteredConnectors.map((connector) => (
              <Col key={connector.id} xs={24} sm={12} md={8} lg={6} xl={6}>
                <ConnectorCard
                  connector={connector}
                  onSelect={handleConnectorSelect}
                  isSelected={selectedConnectorId === connector.id}
                />
              </Col>
            ))}
          </Row>
        )}
      </div>
    </div>
  );
}

ConnectorListModal.propTypes = {
  connectors: PropTypes.array.isRequired,
  onSelectConnector: PropTypes.func.isRequired,
  selectedConnectorId: PropTypes.string,
  loading: PropTypes.bool,
};

export { ConnectorListModal };
