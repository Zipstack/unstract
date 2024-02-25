import { CaretRightOutlined } from "@ant-design/icons";
import {
  Checkbox,
  Col,
  Collapse,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Typography,
  theme,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./AddLlmProfileModal.css";

function AddLlmProfileModal({
  open,
  setOpen,
  editLlmProfileId,
  setEditLlmProfileId,
}) {
  const [name, setName] = useState("");
  const [llm, setLlm] = useState("");
  const [chunkSize, setChunkSize] = useState(1024);
  const [vectorDb, setVectorDb] = useState("");
  const [chunkOverlap, setChunkOverlap] = useState(128);
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [x2TextService, setX2TextService] = useState("");
  const [retrievalStrategy, setRetrievalStrategy] = useState("");
  const [similarityTopK, setSimilarityTopK] = useState(1);
  const [section, setSection] = useState("Default");
  const [reIndex, setReIndex] = useState(false);
  const [retrievalItems, setRetrievalItems] = useState([]);
  const [llmItems, setLlmItems] = useState([]);
  const [vectorDbItems, setVectorDbItems] = useState([]);
  const [embeddingItems, setEmbeddingItems] = useState([]);
  const [x2TextItems, setX2TextItems] = useState([]);
  const [activeKey, setActiveKey] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { getDropdownItems, llmProfiles, updateCustomTool } =
    useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const { token } = theme.useToken();
  const panelStyle = {
    marginBottom: 16,
  };

  useEffect(() => {
    setAdaptorProfilesDropdown();
    const data = getDropdownItems("retrieval_strategy");
    if (!data) {
      return;
    }
    const items = Object.keys(data).map((name) => {
      return {
        value: data[name],
      };
    });
    setRetrievalItems(items);
  }, []);

  useEffect(() => {
    if (open) {
      return;
    }

    setName("");
    setLlm("");
    setChunkSize(1024);
    setVectorDb("");
    setChunkOverlap(128);
    setEmbeddingModel("");
    setX2TextService("");
    setRetrievalStrategy("");
    setSimilarityTopK(1);
    setSection("Default");
    setReIndex(false);
    setEditLlmProfileId(null);
    setActiveKey(false);
  }, [open]);

  useEffect(() => {
    if (!editLlmProfileId) {
      return;
    }

    const llmProfileDetails = [...llmProfiles].find(
      (item) => item?.profile_id === editLlmProfileId
    );

    const llmItem = llmItems.find(
      (item) => item?.label === llmProfileDetails?.llm
    );

    const vectorDbItem = vectorDbItems.find(
      (item) => item?.label === llmProfileDetails?.vector_store
    );

    const embeddingItem = embeddingItems.find(
      (item) => item?.label === llmProfileDetails?.embedding_model
    );

    const x2TextItem = x2TextItems.find(
      (item) => item?.label === llmProfileDetails?.x2text
    );

    setName(llmProfileDetails?.profile_name);
    setLlm(llmItem?.value || null);
    setChunkSize(llmProfileDetails?.chunk_size);
    setVectorDb(vectorDbItem?.value || null);
    setChunkOverlap(llmProfileDetails?.chunk_overlap);
    setEmbeddingModel(embeddingItem?.value || null);
    setX2TextService(x2TextItem?.value || null);
    setRetrievalStrategy(llmProfileDetails?.retrieval_strategy);
    setSimilarityTopK(llmProfileDetails?.similarity_top_k);
    setSection(llmProfileDetails?.section);
    setReIndex(llmProfileDetails?.reindex);
    setActiveKey(true);
  }, [editLlmProfileId]);

  const setAdaptorProfilesDropdown = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;

        data.forEach((item) => {
          if (item?.adapter_type === "LLM") {
            setLlmItems((prev) => {
              const newItems = [...prev];
              newItems.push({
                value: item?.id,
                label: item?.adapter_name,
              });
              return newItems;
            });
          }
          if (item?.adapter_type === "VECTOR_DB") {
            setVectorDbItems((prev) => {
              const newItems = [...prev];
              newItems.push({
                value: item?.id,
                label: item?.adapter_name,
              });
              return newItems;
            });
          }
          if (item?.adapter_type === "EMBEDDING") {
            setEmbeddingItems((prev) => {
              const newItems = [...prev];
              newItems.push({
                value: item?.id,
                label: item?.adapter_name,
              });
              return newItems;
            });
          }
          if (item?.adapter_type === "X2TEXT") {
            setX2TextItems((prev) => {
              const newItems = [...prev];
              newItems.push({
                value: item?.id,
                label: item?.adapter_name,
              });
              return newItems;
            });
          }
        });
      })
      .catch((err) => {
        setAlertDetails(
          handleException(
            err,
            "Failed to get the dropdown list for LLM Adaptors"
          )
        );
      });
  };

  const getItems = (panelStyle) => [
    {
      key: "1",
      label: "Advanced Settings",
      children: (
        <div>
          <Form.Item label="Retrieval Strategy">
            <Select
              options={retrievalItems}
              value={retrievalStrategy}
              onChange={(value) => setRetrievalStrategy(value)}
            />
          </Form.Item>
          <Form.Item label="Matching count limit (similarity top-k)">
            <Input
              type="number"
              value={similarityTopK}
              onChange={(e) => setSimilarityTopK(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="Limit-to Section">
            <Select
              options={[{ value: "Default" }]}
              value={section}
              onChange={(value) => setSection(value)}
            />
          </Form.Item>
          <Row className="add-llm-profile-row">
            <Col span={5}>
              <Form.Item label="Re-Index">
                <Checkbox
                  checked={reIndex}
                  onClick={() => setReIndex(!reIndex)}
                />
              </Form.Item>
            </Col>
          </Row>
        </div>
      ),
      style: panelStyle,
    },
  ];

  const handleSubmit = () => {
    const body = {
      profile_name: name,
      llm,
      vector_store: vectorDb,
      embedding_model: embeddingModel,
      x2text: x2TextService,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      retrieval_strategy: retrievalStrategy,
      similarity_top_k: similarityTopK,
      section,
      reindex: reIndex,
    };

    let method = "POST";
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/profile-manager/`;

    if (editLlmProfileId?.length) {
      method = "PUT";
      url += `${editLlmProfileId}/`;
    }

    const requestOptions = {
      method,
      url,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: body,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        let newLlmProfiles = [...llmProfiles];
        if (editLlmProfileId) {
          newLlmProfiles = [...llmProfiles].map((item) =>
            item?.profile_id === editLlmProfileId ? data : item
          );
        } else {
          newLlmProfiles.push(data);
        }
        const updatedState = {
          llmProfiles: newLlmProfiles,
        };
        updateCustomTool(updatedState);
        setOpen(false);
        setAlertDetails({
          type: "success",
          content: "Saved successfully",
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const handleCollapse = (keys) => {
    setActiveKey(!!keys?.length);
  };

  const handleCaretIcon = (isActive) => {
    return <CaretRightOutlined rotate={isActive ? 90 : 0} />;
  };

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      maskClosable={false}
      centered
      footer={null}
    >
      <Form layout="vertical" onFinish={handleSubmit}>
        <div className="pre-post-amble-body">
          <SpaceWrapper>
            <div>
              <Typography.Text className="add-cus-tool-header">
                Add New LLM Profile
              </Typography.Text>
            </div>
            <div>
              <Form.Item label="Name">
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </Form.Item>
              <Row className="add-llm-profile-row">
                <Col span={15}>
                  <Form.Item label="LLM">
                    <Select
                      options={llmItems}
                      value={llm}
                      onChange={(value) => setLlm(value)}
                    />
                  </Form.Item>
                </Col>
                <Col span={1} />
                <Col span={8}>
                  <Form.Item label="Chunk Size">
                    <Input
                      type="number"
                      value={chunkSize}
                      onChange={(e) => setChunkSize(e.target.value)}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Row className="add-llm-profile-row">
                <Col span={15}>
                  <Form.Item label="Vector Database">
                    <Select
                      options={vectorDbItems}
                      value={vectorDb}
                      onChange={(value) => setVectorDb(value)}
                    />
                  </Form.Item>
                </Col>
                <Col span={1} />
                <Col span={8}>
                  <Form.Item label="Overlap">
                    <Input
                      type="number"
                      value={chunkOverlap}
                      onChange={(e) => setChunkOverlap(e.target.value)}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item label="Embedding Model">
                <Select
                  options={embeddingItems}
                  value={embeddingModel}
                  onChange={(value) => setEmbeddingModel(value)}
                />
              </Form.Item>
              <Form.Item label="Text Extractor">
                <Select
                  options={x2TextItems}
                  value={x2TextService}
                  onChange={(value) => setX2TextService(value)}
                />
              </Form.Item>
              <Collapse
                expandIcon={({ isActive }) => handleCaretIcon(isActive)}
                size="small"
                style={{
                  background: token.colorBgContainer,
                }}
                items={getItems(panelStyle)}
                activeKey={activeKey && "1"}
                onChange={handleCollapse}
              />
            </div>
          </SpaceWrapper>
        </div>
        <Form.Item className="pre-post-amble-footer display-flex-right">
          <Space>
            <CustomButton onClick={() => setOpen(false)}>Cancel</CustomButton>
            <CustomButton type="primary" htmlType="submit">
              {editLlmProfileId ? "Update" : "Add"}
            </CustomButton>
          </Space>
        </Form.Item>
      </Form>
    </Modal>
  );
}

AddLlmProfileModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editLlmProfileId: PropTypes.string,
  setEditLlmProfileId: PropTypes.func.isRequired,
};

export { AddLlmProfileModal };
