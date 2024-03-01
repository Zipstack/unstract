import { CheckCircleFilled } from "@ant-design/icons";
import { Button, Card, Col, Layout, Row, Space } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import logo from "../../assets/UnstractLogoBlack.svg";
import BgShape from "../../assets/bg_shape.svg";
import ConnectEmbedding from "../../assets/connect_embedding.svg";
import ConnectLLM from "../../assets/connect_llm.svg";
import ConnectVectorDb from "../../assets/connect_vector_db.svg";
import { onboardCompleted } from "../../helpers/GetStaticData.js";
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
  const homePageUrl = `/${orgName}/etl`;
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
        "Unstract uses Large Language Models (LLMs) to help structure unstructured data and answer questions from large amounts of unstructured data. We support a wide variety of LLMs from various providers.",
    },
    {
      id: 2,
      title: "CONNECT A VECTOR DATABASE",
      icon: ConnectVectorDb,
      type: "vector_db",
      description:
        "Vector Databases can help find chunks of text from unstructured source data. This helps find relevant data that can then be sent to LLMs to answer your questions or to structure unstructured data.",
    },
    {
      id: 3,
      title: "CHOOSE AN EMBEDDING MODEL",
      icon: ConnectEmbedding,
      type: "embedding",
      description:
        "Embedding models help semantically map unstructured data so that we can then search and retrieve relevant portions of data when structuring or search such data. The quality of the embedding model can affect the quality of relevant data retrieval.",
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
            You&apos;re 3 steps away from nirvana
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
                  <Col span={6} align="center" justify="center">
                    <div className="svg-container">
                      <img src={BgShape} alt="logo bg" className="icon-bg" />
                      <img
                        src={step.icon}
                        alt="Logo"
                        className="icon-overlay"
                      />
                    </div>
                  </Col>
                  <Col span={14}>
                    <Space direction="vertical" style={{ marginTop: "-5px" }}>
                      <h3 className="text-title-style">{step.title}</h3>
                      <p className="text-description-style">
                        {step.description}
                      </p>
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
