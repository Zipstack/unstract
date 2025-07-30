import { useState } from "react";
import { Modal, Radio, Space, Typography, Button, Alert, Divider } from "antd";
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
import "./RetrievalStrategyModal.css";

const { Title, Text, Paragraph } = Typography;

const RETRIEVAL_STRATEGIES = [
  {
    key: "simple",
    title: "Simple Vector Retrieval",
    icon: <SearchOutlined />,
    description:
      "Basic semantic similarity search using vector embeddings with top-k retrieval.",
    bestFor: [
      "Standard document search and Q&A",
      "General knowledge retrieval tasks",
      "Simple semantic similarity matching",
    ],
    tokenUsage: "Low (2-5k tokens typical)",
    costImpact: "Low ($0.01-0.05 per query)",
    technicalDetails:
      "Uses cosine similarity on document embeddings to find the most relevant chunks. Simple and efficient for straightforward retrieval tasks.",
  },
  {
    key: "fusion",
    title: "Fusion Retrieval (RAG Fusion)",
    icon: <ForkOutlined />,
    description:
      "Generates multiple query variations and combines results using Reciprocal Rank Fusion (RRF) for improved relevance.",
    bestFor: [
      "Complex queries requiring comprehensive coverage",
      "Handling ambiguous or multi-faceted questions",
      "Improving recall when simple retrieval misses context",
    ],
    tokenUsage: "High (10-25k tokens typical)",
    costImpact: "High ($0.15-0.40 per query)",
    technicalDetails:
      "Creates 3-5 query variations using LLM, retrieves results for each, then applies RRF scoring to merge and rank results. Significantly improves retrieval quality at higher cost.",
  },
  {
    key: "subquestion",
    title: "Sub-Question Retrieval",
    icon: <QuestionCircleOutlined />,
    description:
      "Decomposes complex queries into sub-questions and retrieves relevant context for each before synthesizing the final answer.",
    bestFor: [
      "Multi-part analytical questions",
      "Research queries requiring multiple perspectives",
      "Complex reasoning tasks spanning multiple topics",
    ],
    tokenUsage: "High (15-30k tokens typical)",
    costImpact: "High ($0.20-0.50 per query)",
    technicalDetails:
      "Uses LlamaIndex SubQuestionQueryEngine to break down complex queries, retrieve context for each sub-question, then synthesize comprehensive answers.",
  },
  {
    key: "recursive",
    title: "Recursive Retrieval",
    icon: <ReloadOutlined />,
    description:
      "Follows document relationships and references recursively to build comprehensive context from connected information.",
    bestFor: [
      "Documents with hierarchical structures",
      "Following citation trails and references",
      "Building context from interconnected content",
    ],
    tokenUsage: "Very High (20-50k tokens typical)",
    costImpact: "Very High ($0.30-0.80 per query)",
    technicalDetails:
      "Uses LlamaIndex RecursiveRetriever with configurable depth limits. Traverses document relationships to gather comprehensive context, ideal for structured documents.",
  },
  {
    key: "router",
    title: "Router-based Retrieval",
    icon: <ShareAltOutlined />,
    description:
      "Intelligently routes queries to different retrieval strategies or data sources based on query analysis.",
    bestFor: [
      "Multi-domain knowledge bases",
      "Adaptive retrieval strategy selection",
      "Handling diverse query types in single system",
    ],
    tokenUsage: "Variable (5-20k tokens typical)",
    costImpact: "Variable ($0.08-0.30 per query)",
    technicalDetails:
      "Uses LlamaIndex RouterQueryEngine to analyze queries and route to appropriate retrievers (vector, keyword, or summary-based) dynamically.",
  },
  {
    key: "keyword_table",
    title: "Keyword Table Retrieval",
    icon: <TableOutlined />,
    description:
      "Extracts and indexes keywords from documents, then performs exact and fuzzy keyword matching for retrieval.",
    bestFor: [
      "Technical documentation with specific terminology",
      "Exact term and phrase matching",
      "Complementing semantic search with keyword precision",
    ],
    tokenUsage: "Low (3-8k tokens typical)",
    costImpact: "Low ($0.02-0.08 per query)",
    technicalDetails:
      "Uses LlamaIndex SimpleKeywordTableIndex to extract keywords during indexing and match against query keywords with TF-IDF scoring.",
  },
  {
    key: "automerging",
    title: "Auto-Merging Retrieval",
    icon: <MergeCellsOutlined />,
    description:
      "Automatically merges adjacent and related document chunks to provide more comprehensive context while avoiding fragmentation.",
    bestFor: [
      "Long-form documents with narrative flow",
      "Maintaining context across chunk boundaries",
      "Reducing information fragmentation",
    ],
    tokenUsage: "Medium (8-18k tokens typical)",
    costImpact: "Medium ($0.10-0.25 per query)",
    technicalDetails:
      "Uses LlamaIndex AutoMergingRetriever to dynamically merge leaf nodes with parent nodes when retrieved chunks are related, preserving document coherence.",
  },
];

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
  const selectedDetails = RETRIEVAL_STRATEGIES.find(
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
    if (usage.includes("High") || usage.includes("Very High")) return "#ff4d4f";
    return "#d9d9d9";
  };

  const getCostImpactColor = (impact) => {
    if (impact.includes("Low")) return "#52c41a";
    if (impact.includes("Medium")) return "#faad14";
    if (impact.includes("High") || impact.includes("Very High"))
      return "#ff4d4f";
    return "#d9d9d9";
  };

  return (
    <Modal
      title="Retrieval Strategy Selection"
      open={visible}
      onCancel={onCancel}
      width={900}
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
      <Alert
        message="Choose Your Retrieval Strategy"
        description="Different retrieval strategies optimize for various use cases. Consider your document types, query complexity, and performance requirements when selecting."
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      {currentStrategy && (
        <div
          style={{
            marginBottom: 16,
            padding: 8,
            backgroundColor: "#f6ffed",
            border: "1px solid #b7eb8f",
            borderRadius: 4,
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            Current:{" "}
            <Text strong>
              {RETRIEVAL_STRATEGIES.find((s) => s.key === currentStrategy)
                ?.title || currentStrategy}
            </Text>
          </Text>
        </div>
      )}

      <div style={{ display: "flex", gap: 16 }}>
        {/* Strategy Selection */}
        <div style={{ flex: 1 }}>
          <Radio.Group
            value={selectedStrategy}
            onChange={handleStrategyChange}
            style={{ width: "100%" }}
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              {RETRIEVAL_STRATEGIES.map((strategy) => (
                <Radio
                  key={strategy.key}
                  value={strategy.key}
                  style={{ width: "100%" }}
                >
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 8 }}
                  >
                    {strategy.icon}
                    <Text strong>{strategy.title}</Text>
                  </div>
                </Radio>
              ))}
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
                  {selectedDetails.bestFor.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
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
                        color: getTokenUsageColor(selectedDetails.tokenUsage),
                      }}
                    >
                      {selectedDetails.tokenUsage}
                    </Text>
                  </div>
                  <div>
                    <Text>Cost Impact: </Text>
                    <Text
                      strong
                      style={{
                        color: getCostImpactColor(selectedDetails.costImpact),
                      }}
                    >
                      {selectedDetails.costImpact}
                    </Text>
                  </div>
                </div>
              </div>

              <Divider />

              <div>
                <Text strong>Technical Details:</Text>
                <Paragraph style={{ marginTop: 8, fontSize: 12 }}>
                  {selectedDetails.technicalDetails}
                </Paragraph>
              </div>
            </>
          )}
        </div>
      </div>
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
