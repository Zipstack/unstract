import debounce from "lodash/debounce";
import { Search } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/shims/antd-inputs";
import { Col, Row } from "@/components/ui/shims/antd-layout";
import { Spin } from "@/components/ui/shims/antd-leaves";
import { Tabs } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";

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

  /*
   * Built inline, `debounce(...)` was a fresh instance on every render, so the
   * effect below scheduled its filter on a brand-new 300ms timer each time and
   * nothing was ever coalesced. `connectors` is a dep because the closure reads
   * it — memoising on [] would filter a stale list once the connectors load.
   *
   * It has to be declared ABOVE the effect now: the dep array is evaluated
   * during render, so naming a `const` that is initialised further down would
   * throw on the temporal dead zone rather than merely read as undefined.
   */
  const filterConnectors = useMemo(
    () =>
      debounce((searchText, mode) => {
        let filtered = [...connectors];

        // Filter by search text
        if (searchText?.trim()) {
          const searchUpper = searchText.toUpperCase().trim();
          filtered = filtered.filter((connector) =>
            connector?.name?.toUpperCase().includes(searchUpper),
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
      }, 300),
    [connectors],
  );

  useEffect(() => {
    filterConnectors(searchText, activeTab);
  }, [filterConnectors, searchText, activeTab]);

  /*
   * Cancel on unmount, and on every `connectors` change: the superseded
   * instance would otherwise still fire and write a filter of the OLD list
   * over the new one.
   */
  useEffect(() => () => filterConnectors.cancel(), [filterConnectors]);

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
        <Typography.Text className="connector-list-loading-text">
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
          prefix={<Search className="search-icon" />}
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
