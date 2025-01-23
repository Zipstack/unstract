import { CheckCircleFilled } from "@ant-design/icons";
import { Button, Card, Col, Layout, Row, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import logo from "../../assets/UnstractLogoBlack.svg";
import ConnectLLM from "../../assets/connect_llm.svg";
import ConnectVectorDb from "../../assets/connect_vector_db.svg";
import ConnectEmbedding from "../../assets/connect_embedding.svg";
import ConnectTextExtractor from "../../assets/connect_x2text.svg";
import { homePagePath, onboardCompleted } from "../../helpers/GetStaticData.js";
import { useSessionStore } from "../../store/session-store.js";
import { AddSourceModal } from "../input-output/add-source-modal/AddSourceModal.jsx";
import { CustomButton } from "../widgets/custom-button/CustomButton.jsx";
import "./onBoard.css";
const { Content } = Layout;

function OnBoard() {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const [openAddSourcesModal, setOpenAddSourcesModal] = useState(false);
  const [editItemId, setEditItemId] = useState(null);
  const [type, setType] = useState(null);
  const homePageUrl = `/${orgName}/${homePagePath}`;
  const [adaptersList, setAdaptersList] = useState(adapters || []);
  useEffect(() => {
    if (onboardCompleted(adaptersList)) {
      navigate(homePageUrl);
    }
  }, [adaptersList]);

  const steps = [
    {
      id: 1,
      title: "CONNECT AN LLM",
      icon: ConnectLLM,
      type: "llm",
      description:
        "Unstract harnesses Large Language Models (LLMs) to organize and analyze vast unstructured data, offering support for diverse LLMs from multiple providers.",
    },
    {
      id: 2,
      title: "CONNECT A VECTOR DATABASE",
      icon: ConnectVectorDb,
      type: "vector_db",
      description:
        "Vector Databases locate text segments within unstructured source data, facilitating the retrieval of pertinent information for LLMs to process queries or structure unstructured data efficiently.",
    },
    {
      id: 3,
      title: "CHOOSE AN EMBEDDING MODEL",
      icon: ConnectEmbedding,
      type: "embedding",
      description:
        "Embedding models semantically map unstructured data for precise retrieval, impacting the quality of data organization and search relevance.",
    },
    {
      id: 4,
      title: "CONNECT A TEXT EXTRACTOR",
      icon: ConnectTextExtractor,
      type: "x2text",
      description:
        "The Text Extractor extracts text from diverse unstructured documents, optimizing input for LLM comprehension, including OCR as needed, ensuring optimal understanding of content.",
    },
  ];

  const showOpenAddSourcesModal = (type) => {
    setType(type);
    setOpenAddSourcesModal(true);
  };

  const addNewItem = (row, isEdit) => {
    const newAdapter = row?.adapter_type.toLowerCase();
    setAdaptersList([...adaptersList, newAdapter]);
  };

  return (
    <>
      <Content className="onboard-content">
        <div>
          <img src={logo} alt="Logo" className="landing-logo" />
          <h1 className="uppercase-text">
            You&apos;re 4 steps away from nirvana
          </h1>
          <Space direction="vertical">
            {steps.map((step, index) => (
              <Card key={step.id} className="card-style">
                <div className="card-container">
                  <div className="circle">
                    <div className="circle-number">{step.id}</div>
                  </div>
                </div>
                <Row align="middle">
                  <Col span={3} align="" justify="">
                    <div className="">
                      <img
                        src={step.icon}
                        alt="Logo"
                        className="icon-overlay"
                      />
                    </div>
                  </Col>
                  <Col span={17}>
                    <Space direction="vertical" style={{ marginTop: "-5px" }}>
                      <h3 className="text-title-style">{step.title}</h3>
                      <Typography.Text className="text-description-style">
                        {step.description}
                      </Typography.Text>
                    </Space>
                  </Col>
                  <Col span={4} align="center" justify="center">
                    {adaptersList?.includes(step.type) ? (
                      <div>
                        <CheckCircleFilled className="configured-icon" />
                        <span className="configured-text">Configured</span>
                      </div>
                    ) : (
                      <Button
                        className="button-style"
                        onClick={() => showOpenAddSourcesModal(step.type)}
                      >
                        Connect
                      </Button>
                    )}
                  </Col>
                </Row>
              </Card>
            ))}
          </Space>
          <div className="later-div-style">
            <div className="help-text">
              Need help? Here&apos;s our&nbsp;
              <a
                href="https://docs.unstract.com/"
                target="_blank"
                rel="noreferrer"
                className="link-color"
              >
                quick start guide&nbsp;
              </a>
              to help you get going.
            </div>
            <CustomButton type="primary" onClick={() => navigate(homePageUrl)}>
              Complete Later &gt;
            </CustomButton>
          </div>
        </div>
      </Content>
      <AddSourceModal
        open={openAddSourcesModal}
        setOpen={setOpenAddSourcesModal}
        type={type}
        addNewItem={addNewItem}
        editItemId={editItemId}
        setEditItemId={setEditItemId}
      />
    </>
  );
}

export { OnBoard };
