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

import {
  getBackendErrorDetail,
  handleException,
} from "../../../helpers/GetStaticData";
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
  const [form] = Form.useForm();
  const [formDetails, setFormDetails] = useState({});
  const [resetForm, setResetForm] = useState(false);
  const [backendErrors, setBackendErrors] = useState(null);
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
    if (!open) {
      return;
    }

    setResetForm(true);
    setFormDetails({
      profile_name: "",
      llm: "",
      chunk_size: 1024,
      vector_store: "",
      chunk_overlap: 128,
      embedding_model: "",
      x2text: "",
      retrieval_strategy: "simple",
      similarity_top_k: 1,
      section: "Default",
      reindex: false,
    });

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

    setResetForm(true);
    setFormDetails({
      profile_name: llmProfileDetails?.profile_name,
      llm: llmItem?.value || null,
      chunk_size: llmProfileDetails?.chunk_size,
      vector_store: vectorDbItem?.value || null,
      chunk_overlap: llmProfileDetails?.chunk_overlap,
      embedding_model: embeddingItem?.value || null,
      x2text: x2TextItem?.value || null,
      retrieval_strategy: llmProfileDetails?.retrieval_strategy,
      similarity_top_k: llmProfileDetails?.similarity_top_k,
      section: llmProfileDetails?.section,
      reindex: llmProfileDetails?.reindex,
    });
    setActiveKey(true);
  }, [editLlmProfileId]);

  useEffect(() => {
    if (resetForm) {
      form.resetFields();
      setResetForm(false);
    }
  }, [formDetails]);

  const validateEmptyOrWhitespace = (_, value) => {
    if (value && value.trim() === "") {
      return Promise.reject(new Error("Please enter a non-whitespace value"));
    }
    return Promise.resolve(); // Resolve if value is empty or contains only whitespaces
  };

  const handleInputChange = (changedValues, allValues) => {
    setFormDetails({ ...formDetails, ...allValues });
    const changedFieldName = Object.keys(changedValues)[0];
    form.setFields([
      {
        name: changedFieldName,
        errors: [],
      },
    ]);
    setBackendErrors((prevErrors) => {
      if (prevErrors) {
        const updatedErrors = prevErrors.errors.filter(
          (error) => error.attr !== changedFieldName
        );
        return { ...prevErrors, errors: updatedErrors };
      }
      return null;
    });
  };

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
          <Form.Item
            label="Retrieval Strategy"
            name="retrieval_strategy"
            validateStatus={
              getBackendErrorDetail("retrieval_strategy", backendErrors)
                ? "error"
                : ""
            }
            help={getBackendErrorDetail("retrieval_strategy", backendErrors)}
          >
            <Select options={retrievalItems} />
          </Form.Item>
          <Form.Item
            label="Matching count limit (similarity top-k)"
            name="similarity_top_k"
            validateStatus={
              getBackendErrorDetail("similarity_top_k", backendErrors)
                ? "error"
                : ""
            }
            help={getBackendErrorDetail("similarity_top_k", backendErrors)}
          >
            <Input type="number" />
          </Form.Item>
          <Form.Item
            label="Limit-to Section"
            name="section"
            validateStatus={
              getBackendErrorDetail("section", backendErrors) ? "error" : ""
            }
            help={getBackendErrorDetail("section", backendErrors)}
          >
            <Select options={[{ value: "Default" }]} />
          </Form.Item>
          <Row className="add-llm-profile-row">
            <Col span={5}>
              <Form.Item label="Re-Index">
                <Checkbox />
              </Form.Item>
            </Col>
          </Row>
        </div>
      ),
      style: panelStyle,
    },
  ];

  const handleSubmit = () => {
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
      data: formDetails,
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
      <Form
        form={form}
        layout="vertical"
        initialValues={formDetails}
        onValuesChange={handleInputChange}
        onFinish={handleSubmit}
      >
        <div className="pre-post-amble-body">
          <SpaceWrapper>
            <div>
              <Typography.Text className="add-cus-tool-header">
                Add New LLM Profile
              </Typography.Text>
            </div>
            <div>
              <Form.Item
                label="Name"
                name="profile_name"
                rules={[
                  {
                    required: true,
                    message: "Please enter the name",
                  },
                  { validator: validateEmptyOrWhitespace },
                ]}
                validateStatus={
                  getBackendErrorDetail("profile_name", backendErrors)
                    ? "error"
                    : ""
                }
                help={getBackendErrorDetail("profile_name", backendErrors)}
              >
                <Input />
              </Form.Item>
              <Row className="add-llm-profile-row">
                <Col span={15}>
                  <Form.Item
                    label="LLM"
                    name="llm"
                    rules={[
                      { required: true, message: "Please enter the LLM" },
                      { validator: validateEmptyOrWhitespace },
                    ]}
                    validateStatus={
                      getBackendErrorDetail("llm", backendErrors) ? "error" : ""
                    }
                    help={getBackendErrorDetail("llm", backendErrors)}
                  >
                    <Select options={llmItems} />
                  </Form.Item>
                </Col>
                <Col span={1} />
                <Col span={8}>
                  <Form.Item
                    label="Chunk Size"
                    name="chunk_size"
                    rules={[
                      {
                        required: true,
                        message: "Please enter the chunk size",
                      },
                    ]}
                    validateStatus={
                      getBackendErrorDetail("chunk_size", backendErrors)
                        ? "error"
                        : ""
                    }
                    help={getBackendErrorDetail("chunk_size", backendErrors)}
                  >
                    <Input type="number" />
                  </Form.Item>
                </Col>
              </Row>
              <Row className="add-llm-profile-row">
                <Col span={15}>
                  <Form.Item
                    label="Vector Database"
                    name="vector_store"
                    rules={[
                      {
                        required: true,
                        message: "Please select the vector store",
                      },
                      { validator: validateEmptyOrWhitespace },
                    ]}
                    validateStatus={
                      getBackendErrorDetail("vector_store", backendErrors)
                        ? "error"
                        : ""
                    }
                    help={getBackendErrorDetail("vector_store", backendErrors)}
                  >
                    <Select options={vectorDbItems} />
                  </Form.Item>
                </Col>
                <Col span={1} />
                <Col span={8}>
                  <Form.Item
                    label="Overlap"
                    name="chunk_overlap"
                    rules={[
                      {
                        required: true,
                        message: "Please enter the overlap",
                      },
                    ]}
                    validateStatus={
                      getBackendErrorDetail("chunk_overlap", backendErrors)
                        ? "error"
                        : ""
                    }
                    help={getBackendErrorDetail("chunk_overlap", backendErrors)}
                  >
                    <Input type="number" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item
                label="Embedding Model"
                name="embedding_model"
                rules={[
                  {
                    required: true,
                    message: "Please select the embedding model",
                  },
                  { validator: validateEmptyOrWhitespace },
                ]}
                validateStatus={
                  getBackendErrorDetail("embedding_model", backendErrors)
                    ? "error"
                    : ""
                }
                help={getBackendErrorDetail("embedding_model", backendErrors)}
              >
                <Select options={embeddingItems} />
              </Form.Item>
              <Form.Item
                label="Text Extractor"
                name="x2text"
                rules={[
                  {
                    required: true,
                    message: "Please select the text extractor",
                  },
                  { validator: validateEmptyOrWhitespace },
                ]}
                validateStatus={
                  getBackendErrorDetail("x2text", backendErrors) ? "error" : ""
                }
                help={getBackendErrorDetail("x2text", backendErrors)}
              >
                <Select options={x2TextItems} />
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
