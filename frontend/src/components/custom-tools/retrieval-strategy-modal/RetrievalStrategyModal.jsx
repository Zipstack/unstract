import { useState, useEffect } from "react";
import {
  Modal,
  Radio,
  Space,
  Typography,
  Button,
  Alert,
  Divider,
  Spin,
} from "antd";
import {
  SearchOutlined,
  QuestionCircleOutlined,
  ForkOutlined,
  ReloadOutlined,
  ShareAltOutlined,
  TableOutlined,
  MergeCellsOutlined,
} from "@ant-design/icons";
import PropTypes from "prop-types";
import { useParams } from "react-router-dom";

import { useRetrievalStrategies } from "../../../hooks/useRetrievalStrategies";
import "./RetrievalStrategyModal.css";

const { Title, Text, Paragraph } = Typography;

const ICON_MAP = {
  SearchOutlined: <SearchOutlined />,
  QuestionCircleOutlined: <QuestionCircleOutlined />,
  ForkOutlined: <ForkOutlined />,
  ReloadOutlined: <ReloadOutlined />,
  ShareAltOutlined: <ShareAltOutlined />,
  TableOutlined: <TableOutlined />,
  MergeCellsOutlined: <MergeCellsOutlined />,
};

const RetrievalStrategyModal = ({
  visible,
  onCancel,
  onOk,
  currentStrategy = "simple",
  loading = false,
}) => {
  const [selectedStrategy, setSelectedStrategy] = useState(
    currentStrategy || "simple"
  );
  const { id } = useParams();
  const {
    strategies,
    isLoading: isLoadingStrategies,
    getStrategies,
  } = useRetrievalStrategies();

  useEffect(() => {
    if (visible && id) {
      getStrategies(id);
    }
  }, [visible, id, getStrategies]);

  const retrievalStrategies = strategies || [];

  // Transform strategies to include React icons
  const strategiesWithIcons = retrievalStrategies.map((strategy) => ({
    ...strategy,
    icon: ICON_MAP[strategy.icon] || <SearchOutlined />,
  }));

  const selectedDetails = strategiesWithIcons.find(
    (s) => s.key === selectedStrategy
  );

  const handleStrategyChange = (e) => {
    setSelectedStrategy(e.target.value);
  };

  const handleSubmit = () => {
    onOk(selectedStrategy);
  };

  const getTokenUsageColor = (usage) => {
    if (usage.includes("Low")) return "#52c41a";
    if (usage.includes("Medium")) return "#faad14";
    if (usage.includes("Very High")) return "#ff4d4f";
    if (usage.includes("High")) return "#ff4d4f";
    return "#d9d9d9";
  };

  const getCostImpactColor = (impact) => {
    if (impact.includes("Low")) return "#52c41a";
    if (impact.includes("Medium")) return "#faad14";
    if (impact.includes("Very High")) return "#ff4d4f";
    if (impact.includes("High")) return "#ff4d4f";
    return "#d9d9d9";
  };

  return (
    <Modal
      title="Retrieval Strategy Selection"
      open={visible}
      onCancel={onCancel}
      width={900}
      aria-label="Retrieval Strategy Selection Dialog"
      aria-describedby="retrieval-strategy-description"
      footer={[
        <Button key="cancel" onClick={onCancel}>
          Cancel
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={handleSubmit}
          loading={loading}
        >
          Select Strategy
        </Button>,
      ]}
      className="retrieval-strategy-modal"
    >
      {isLoadingStrategies ? (
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <Spin size="large" tip="Loading strategies..." />
        </div>
      ) : (
        <>
          <Alert
            id="retrieval-strategy-description"
            message="Choose Your Retrieval Strategy"
            description="Different retrieval strategies optimize for various use cases. Consider your document types, query complexity, and performance requirements when selecting."
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <div style={{ display: "flex", gap: 16 }}>
            {/* Strategy Selection */}
            <div style={{ flex: 1 }}>
              <Radio.Group
                value={selectedStrategy}
                onChange={handleStrategyChange}
                style={{ width: "100%" }}
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  {strategiesWithIcons.length > 0 ? (
                    strategiesWithIcons.map((strategy) => (
                      <Radio
                        key={strategy.key}
                        value={strategy.key}
                        style={{ width: "100%" }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          {strategy.icon}
                          <Text strong>{strategy.title}</Text>
                          {strategy.key === currentStrategy && (
                            <Text
                              type="success"
                              style={{
                                fontSize: 12,
                                marginLeft: 8,
                                fontWeight: "normal",
                              }}
                            >
                              (Selected)
                            </Text>
                          )}
                        </div>
                      </Radio>
                    ))
                  ) : (
                    <div style={{ textAlign: "center", padding: "20px 0" }}>
                      <Text type="secondary">
                        No retrieval strategies available. Please try refreshing
                        the page.
                      </Text>
                    </div>
                  )}
                </Space>
              </Radio.Group>
            </div>

            {/* Strategy Details */}
            <div
              style={{
                flex: 1.5,
                paddingLeft: 16,
                borderLeft: "1px solid #f0f0f0",
              }}
            >
              {selectedDetails && (
                <>
                  <Title level={4} style={{ marginBottom: 8 }}>
                    {selectedDetails.title}
                  </Title>

                  <Paragraph style={{ marginBottom: 16 }}>
                    {selectedDetails.description}
                  </Paragraph>

                  <div style={{ marginBottom: 16 }}>
                    <Text strong>Best For:</Text>
                    <ul style={{ marginTop: 8, marginBottom: 0 }}>
                      {selectedDetails.bestFor &&
                      selectedDetails.bestFor.length > 0 ? (
                        selectedDetails.bestFor.map((item) => (
                          <li key={item}>{item}</li>
                        ))
                      ) : (
                        <li>No specific use cases defined</li>
                      )}
                    </ul>
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <Text strong>Performance Impact:</Text>
                    <div style={{ marginTop: 8 }}>
                      <div style={{ marginBottom: 8 }}>
                        <Text>Token Usage: </Text>
                        <Text
                          strong
                          style={{
                            color: getTokenUsageColor(
                              selectedDetails.tokenUsage || "Unknown"
                            ),
                          }}
                        >
                          {selectedDetails.tokenUsage || "Unknown"}
                        </Text>
                      </div>
                      <div>
                        <Text>Cost Impact: </Text>
                        <Text
                          strong
                          style={{
                            color: getCostImpactColor(
                              selectedDetails.costImpact || "Unknown"
                            ),
                          }}
                        >
                          {selectedDetails.costImpact || "Unknown"}
                        </Text>
                      </div>
                    </div>
                  </div>

                  <Divider />

                  <div>
                    <Text strong>Technical Details:</Text>
                    <Paragraph style={{ marginTop: 8, fontSize: 12 }}>
                      {selectedDetails.technicalDetails ||
                        "No technical details available"}
                    </Paragraph>
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </Modal>
  );
};

RetrievalStrategyModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onOk: PropTypes.func.isRequired,
  currentStrategy: PropTypes.string,
  loading: PropTypes.bool,
};

export default RetrievalStrategyModal;
