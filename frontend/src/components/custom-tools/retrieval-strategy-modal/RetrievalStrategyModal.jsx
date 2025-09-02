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

  // Update selectedStrategy when currentStrategy prop changes or modal opens
  useEffect(() => {
    if (visible && currentStrategy) {
      setSelectedStrategy(currentStrategy);
    }
  }, [currentStrategy, visible]);
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

  const getTokenUsageClassName = (usage) => {
    if (usage.includes("Low"))
      return "retrieval-strategy-modal__token-usage-low";
    if (usage.includes("Medium"))
      return "retrieval-strategy-modal__token-usage-medium";
    if (usage.includes("Very High"))
      return "retrieval-strategy-modal__token-usage-high";
    if (usage.includes("High"))
      return "retrieval-strategy-modal__token-usage-high";
    return "";
  };

  const getCostImpactClassName = (impact) => {
    if (impact.includes("Low"))
      return "retrieval-strategy-modal__cost-impact-low";
    if (impact.includes("Medium"))
      return "retrieval-strategy-modal__cost-impact-medium";
    if (impact.includes("Very High"))
      return "retrieval-strategy-modal__cost-impact-high";
    if (impact.includes("High"))
      return "retrieval-strategy-modal__cost-impact-high";
    return "";
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
        <div className="retrieval-strategy-modal__loading">
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
            className="retrieval-strategy-modal__alert"
          />

          <div className="retrieval-strategy-modal__content">
            {/* Strategy Selection */}
            <div className="retrieval-strategy-modal__selection">
              <Radio.Group
                value={selectedStrategy}
                onChange={handleStrategyChange}
                className="retrieval-strategy-modal__radio-group"
              >
                <Space
                  direction="vertical"
                  className="retrieval-strategy-modal__radio-space"
                >
                  {strategiesWithIcons.length > 0 ? (
                    strategiesWithIcons.map((strategy) => (
                      <Radio
                        key={strategy?.key}
                        value={strategy?.key}
                        className="retrieval-strategy-modal__radio-item"
                      >
                        <div className="retrieval-strategy-modal__radio-content">
                          {strategy?.icon}
                          <Text strong>{strategy?.title}</Text>
                          {strategy?.key === currentStrategy && (
                            <Text
                              type="success"
                              className="retrieval-strategy-modal__selected-indicator"
                            >
                              (Selected)
                            </Text>
                          )}
                        </div>
                      </Radio>
                    ))
                  ) : (
                    <div className="retrieval-strategy-modal__empty-state">
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
            <div className="retrieval-strategy-modal__details">
              {selectedDetails && (
                <>
                  <Title level={4} className="retrieval-strategy-modal__title">
                    {selectedDetails?.title}
                  </Title>

                  <Paragraph className="retrieval-strategy-modal__description">
                    {selectedDetails?.description}
                  </Paragraph>

                  <div className="retrieval-strategy-modal__best-for">
                    <Text strong>Best For:</Text>
                    <ul className="retrieval-strategy-modal__best-for-list">
                      {selectedDetails?.bestFor &&
                      selectedDetails?.bestFor?.length > 0 ? (
                        selectedDetails.bestFor.map((item) => (
                          <li key={item}>{item}</li>
                        ))
                      ) : (
                        <li>No specific use cases defined</li>
                      )}
                    </ul>
                  </div>

                  <div className="retrieval-strategy-modal__performance">
                    <Text strong>Performance Impact:</Text>
                    <div className="retrieval-strategy-modal__performance-content">
                      <div className="retrieval-strategy-modal__performance-item">
                        <Text>Token Usage: </Text>
                        <Text
                          strong
                          className={getTokenUsageClassName(
                            selectedDetails?.tokenUsage || "Unknown"
                          )}
                        >
                          {selectedDetails?.tokenUsage || "Unknown"}
                        </Text>
                      </div>
                      <div>
                        <Text>Cost Impact: </Text>
                        <Text
                          strong
                          className={getCostImpactClassName(
                            selectedDetails?.costImpact || "Unknown"
                          )}
                        >
                          {selectedDetails?.costImpact || "Unknown"}
                        </Text>
                      </div>
                    </div>
                  </div>

                  <Divider />

                  <div>
                    <Text strong>Technical Details:</Text>
                    <Paragraph className="retrieval-strategy-modal__technical-details">
                      {selectedDetails?.technicalDetails ||
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
