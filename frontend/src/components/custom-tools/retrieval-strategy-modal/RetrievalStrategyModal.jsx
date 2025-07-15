// RetrievalStrategyModal component - Sidebar Navigation Design
import { useState } from "react";
import PropTypes from "prop-types";
import { Modal, Typography, Divider, Space, Tag, Tooltip, Alert } from "antd";
import {
  InfoCircleOutlined,
  DollarOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  ExperimentOutlined,
  QuestionCircleOutlined,
  SearchOutlined,
  SplitCellsOutlined,
  MergeCellsOutlined,
  BranchesOutlined,
  TableOutlined,
} from "@ant-design/icons";
import "./RetrievalStrategyModal.css";

const { Title, Paragraph, Text } = Typography;

const strategiesInfo = [
  {
    key: "simple",
    name: "Simple Vector Retrieval",
    icon: <SearchOutlined />,
    description:
      "Standard vector similarity search that finds documents semantically similar to the query.",
    bestFor: [
      "General purpose queries",
      "When document context is clear and straightforward",
      "Most everyday use cases",
    ],
    tokenImpact: "Low",
    costImpact: "Low",
    technicalDetails:
      "Uses cosine similarity between the query vector and document vectors to find the most relevant matches.",
    costPlaceholder: "Cost placeholder for simple retrieval",
    tokenPlaceholder: "Token placeholder for simple retrieval",
  },
  {
    key: "subquestion",
    name: "Subquestion Retrieval",
    icon: <QuestionCircleOutlined />,
    description:
      "Breaks complex queries into simpler sub-questions to gather more comprehensive information.",
    bestFor: [
      "Complex multi-part questions",
      "When a single query isn't sufficient",
      "Research-oriented queries requiring multiple perspectives",
    ],
    tokenImpact: "Medium-High",
    costImpact: "Medium-High",
    technicalDetails:
      "Utilizes LlamaIndex's SubQuestionQueryEngine to decompose questions and aggregate responses.",
    costPlaceholder: "Cost placeholder for subquestion retrieval",
    tokenPlaceholder: "Token placeholder for subquestion retrieval",
  },
  {
    key: "fusion",
    name: "Fusion Retrieval",
    icon: <SplitCellsOutlined />,
    description:
      "Combines vector similarity search with BM25 keyword search for robust results.",
    bestFor: [
      "Queries with both semantic meaning and specific keywords",
      "When keyword precision and semantic understanding are both important",
      "Balancing exact match and contextual relevance",
    ],
    tokenImpact: "Medium",
    costImpact: "Medium",
    technicalDetails:
      "Uses LlamaIndex's QueryFusionRetriever to combine vector and keyword search results with weighted relevance scoring.",
    costPlaceholder: "Cost placeholder for fusion retrieval",
    tokenPlaceholder: "Token placeholder for fusion retrieval",
  },
  {
    key: "recursive",
    name: "Recursive Retrieval",
    icon: <BranchesOutlined />,
    description:
      "Follows content relationships recursively to explore connected information.",
    bestFor: [
      "Exploring document relationships and connections",
      "Following citation trails or references",
      "Understanding hierarchical or nested content",
    ],
    tokenImpact: "High",
    costImpact: "High",
    technicalDetails:
      "Leverages LlamaIndex's RecursiveRetriever to traverse document connections with configurable depth.",
    costPlaceholder: "Cost placeholder for recursive retrieval",
    tokenPlaceholder: "Token placeholder for recursive retrieval",
  },
  {
    key: "router",
    name: "Router Retrieval",
    icon: <ExperimentOutlined />,
    description:
      "Intelligently selects the best retrieval method based on the query characteristics.",
    bestFor: [
      "Mixed query workloads with varying characteristics",
      "When you're unsure which retrieval strategy is best",
      "Optimizing retrieval performance automatically",
    ],
    tokenImpact: "Medium-High",
    costImpact: "Medium-High",
    technicalDetails:
      "Uses LlamaIndex's RouterRetriever to dynamically choose between semantic, keyword, and hybrid approaches.",
    costPlaceholder: "Cost placeholder for router retrieval",
    tokenPlaceholder: "Token placeholder for router retrieval",
  },
  {
    key: "keyword_table",
    name: "Keyword Table Retrieval",
    icon: <TableOutlined />,
    description:
      "Uses precise keyword matching for technical content and exact term searching.",
    bestFor: [
      "Technical documentation with specific terminology",
      "Exact keyword matching needs",
      "When semantic similarity isn't sufficient",
    ],
    tokenImpact: "Low-Medium",
    costImpact: "Low-Medium",
    technicalDetails:
      "Employs LlamaIndex's KeywordTableIndex for efficient exact and fuzzy keyword matching.",
    costPlaceholder: "Cost placeholder for keyword table retrieval",
    tokenPlaceholder: "Token placeholder for keyword table retrieval",
  },
  {
    key: "auto_merging",
    name: "AutoMerging Retrieval",
    icon: <MergeCellsOutlined />,
    description:
      "Automatically merges similar content chunks for more comprehensive context.",
    bestFor: [
      "When context is fragmented across multiple chunks",
      "Documents with repetitive information",
      "Consolidating related information",
    ],
    tokenImpact: "Medium-High",
    costImpact: "Medium",
    technicalDetails:
      "Uses LlamaIndex's AutoMergingRetriever to identify and combine similar content with configurable similarity threshold.",
    costPlaceholder: "Cost placeholder for auto merging retrieval",
    tokenPlaceholder: "Token placeholder for auto merging retrieval",
  },
];

const RetrievalStrategyModal = ({
  visible,
  onCancel,
  onSelectStrategy,
  currentStrategy,
}) => {
  const [selectedStrategy, setSelectedStrategy] = useState(
    currentStrategy || "simple"
  );

  return (
    <Modal
      title={
        <Space>
          <CodeOutlined />
          <span>Retrieval Strategy Selection</span>
        </Space>
      }
      open={visible}
      onCancel={onCancel}
      width={900}
      footer={null}
      className="retrieval-strategy-modal"
    >
      <Alert
        message="Technical Feature"
        description="Retrieval strategies affect how documents are searched and context is gathered. Choosing the right strategy can significantly impact the quality and relevance of responses."
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <div className="strategy-layout">
        <div className="strategy-sidebar">
          {strategiesInfo.map((strategy) => (
            <div
              key={strategy.key}
              className={`strategy-sidebar-item ${
                selectedStrategy === strategy.key ? "selected" : ""
              }`}
              onClick={() => setSelectedStrategy(strategy.key)}
            >
              <div className="strategy-sidebar-icon">{strategy.icon}</div>
              <div className="strategy-sidebar-text">{strategy.name}</div>
            </div>
          ))}
        </div>

        <div className="strategy-content-container">
          {strategiesInfo.map(
            (strategy) =>
              strategy.key === selectedStrategy && (
                <div key={strategy.key} className="strategy-content">
                  <div className="strategy-header">
                    <Title level={4}>{strategy.name}</Title>
                    <button
                      className="select-strategy-btn"
                      onClick={() => onSelectStrategy(strategy.key)}
                    >
                      Select {strategy.name}
                    </button>
                  </div>
                  <Paragraph>{strategy.description}</Paragraph>

                  <Divider orientation="left">Best For</Divider>
                  <ul>
                    {strategy.bestFor.map((item, index) => (
                      <li key={index}>
                        <Text>{item}</Text>
                      </li>
                    ))}
                  </ul>

                  <Divider orientation="left">Resource Impact</Divider>
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <div>
                      <Space>
                        <ClockCircleOutlined />
                        <Text strong>Token Usage:</Text>
                        <Tag
                          color={
                            strategy.tokenImpact === "Low"
                              ? "success"
                              : strategy.tokenImpact === "Medium"
                              ? "warning"
                              : "error"
                          }
                        >
                          {strategy.tokenImpact}
                        </Tag>
                      </Space>
                      <div className="impact-details">
                        <Text type="secondary">
                          <Tooltip title="This will be filled from documentation">
                            <InfoCircleOutlined style={{ marginRight: 5 }} />
                          </Tooltip>
                          {strategy.tokenPlaceholder}
                        </Text>
                      </div>
                    </div>

                    <div>
                      <Space>
                        <DollarOutlined />
                        <Text strong>Cost Impact:</Text>
                        <Tag
                          color={
                            strategy.costImpact === "Low"
                              ? "success"
                              : strategy.costImpact === "Medium"
                              ? "warning"
                              : "error"
                          }
                        >
                          {strategy.costImpact}
                        </Tag>
                      </Space>
                      <div className="impact-details">
                        <Text type="secondary">
                          <Tooltip title="This will be filled from documentation">
                            <InfoCircleOutlined style={{ marginRight: 5 }} />
                          </Tooltip>
                          {strategy.costPlaceholder}
                        </Text>
                      </div>
                    </div>
                  </Space>

                  <Divider orientation="left">Technical Details</Divider>
                  <Paragraph>
                    <CodeOutlined style={{ marginRight: 8 }} />
                    {strategy.technicalDetails}
                  </Paragraph>

                  <div className="strategy-action">
                    <button
                      className="select-strategy-btn"
                      onClick={() => onSelectStrategy(strategy.key)}
                    >
                      Select {strategy.name}
                    </button>
                  </div>
                </div>
              )
          )}
        </div>
      </div>
    </Modal>
  );
};

RetrievalStrategyModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onCancel: PropTypes.func.isRequired,
  onSelectStrategy: PropTypes.func.isRequired,
  currentStrategy: PropTypes.string,
};

export default RetrievalStrategyModal;
