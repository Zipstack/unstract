import { useState } from "react";
import { Modal, Button, Row, Col, Tag, Divider } from "antd";

const versions = [
  {
    version: "v1",
    name: "monthly_revenue",
    description:
      "What is the revenue per month for this organization in USD. Do not add the dollar symbol or make it human readable by adding commas.",
    model: "GPT3.5 Turbo",
    database: "Milvus",
    indexing: "FAISS",
    type: "text",
  },
  {
    version: "v2",
    name: "monthly_revenue",
    description:
      "Respond with the revenue per month for this organization in USD. Do not add the dollar symbol or make it human readable by adding commas. Just output the actual number.",
    model: "GPT3.5 Turbo",
    database: "PostgreSQL with Vector",
    indexing: "FAISS",
    type: "number",
  },
  {
    version: "v3",
    name: "monthly_revenue",
    description:
      "What is the revenue per month for this organization in USD. Do not add the dollar symbol or make it human readable by adding commas. Just output the actual number.",
    model: "GPT3.5 Turbo",
    database: "Milvus",
    indexing: "FAISS",
    type: "number",
  },
  {
    version: "v4",
    name: "monthly_revenue_usd",
    description:
      "What is the revenue per month for this organization in USD. Do not add the dollar symbol or make it human readable by adding commas. Just output the actual number.",
    model: "GPT3.5 Turbo",
    database: "Milvus",
    indexing: "FAISS",
    type: "number",
    current: true,
  },
];

const PromptVersionModal = () => {
  const [isModalVisible, setIsModalVisible] = useState(false);

  const showModal = () => {
    setIsModalVisible(true);
  };

  const handleOk = () => {
    setIsModalVisible(false);
  };

  const handleCancel = () => {
    setIsModalVisible(false);
  };

  return (
    <>
      <Button type="primary" onClick={showModal}>
        Open Modal
      </Button>
      <Modal
        title="Versions"
        open={isModalVisible}
        onOk={handleOk}
        onCancel={handleCancel}
      >
        {versions.map((version, index) => (
          <div key={index} style={{ marginBottom: 16 }}>
            <Row gutter={16} align="middle">
              <Col span={4}>
                <Tag color="blue">{version.version}</Tag>
              </Col>
              <Col span={10}>
                <div
                  style={{ fontWeight: version.current ? "bold" : "normal" }}
                >
                  {version.name}
                </div>
                <div>{version.description}</div>
              </Col>
              <Col span={6}>
                <Tag color="green">{version.model}</Tag>
                <Tag color="gold">{version.database}</Tag>
                <Tag color="magenta">{version.indexing}</Tag>
              </Col>
              <Col span={4}>
                <Button type="primary" disabled={version.current}>
                  Load
                </Button>
              </Col>
            </Row>
            <Divider />
          </div>
        ))}
      </Modal>
    </>
  );
};

export { PromptVersionModal };
