import {
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Row,
  Col,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import "./ProfileFormModal.css";

const { Option } = Select;

function ProfileFormModal({ projectId, profileId, onClose }) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [adaptersLoading, setAdaptersLoading] = useState(false);

  const [llmItems, setLlmItems] = useState([]);
  const [vectorDbItems, setVectorDbItems] = useState([]);
  const [embeddingItems, setEmbeddingItems] = useState([]);
  const [x2TextItems, setX2TextItems] = useState([]);
  const [adaptersLoaded, setAdaptersLoaded] = useState(false);

  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const isEdit = !!profileId;
  const modalTitle = isEdit ? "Edit Profile" : "Add New Profile";

  // Fetch adapters
  useEffect(() => {
    fetchAdapters();
  }, []);

  // Load profile data for editing (only after adapters are loaded)
  useEffect(() => {
    if (profileId && adaptersLoaded) {
      fetchProfileData();
    }
  }, [profileId, adaptersLoaded]);

  const fetchAdapters = () => {
    setAdaptersLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data || [];

        const llmList = [];
        const vectorDbList = [];
        const embeddingList = [];
        const x2TextList = [];

        data.forEach((item) => {
          const option = {
            value: item?.id,
            label: item?.adapter_name,
          };

          if (item?.adapter_type === "LLM") {
            llmList.push(option);
          } else if (item?.adapter_type === "VECTOR_DB") {
            vectorDbList.push(option);
          } else if (item?.adapter_type === "EMBEDDING") {
            embeddingList.push(option);
          } else if (item?.adapter_type === "X2TEXT") {
            x2TextList.push(option);
          }
        });

        setLlmItems(llmList);
        setVectorDbItems(vectorDbList);
        setEmbeddingItems(embeddingList);
        setX2TextItems(x2TextList);
      })
      .catch((err) => {
        handleException(err, "Failed to fetch adapters");
      })
      .finally(() => {
        setAdaptersLoading(false);
        setAdaptersLoaded(true);
      });
  };

  const fetchProfileData = () => {
    setLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/${profileId}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const profile = res?.data;

        // Find adapter IDs by matching adapter names from the profile response
        // The API returns adapter names as strings (e.g., "Azure LLM")
        const llmItem = llmItems.find((item) => item?.label === profile?.llm);
        const embeddingItem = embeddingItems.find(
          (item) => item?.label === profile?.embedding_model
        );
        const vectorDbItem = vectorDbItems.find(
          (item) => item?.label === profile?.vector_store
        );
        const x2textItem = x2TextItems.find(
          (item) => item?.label === profile?.x2text
        );

        form.setFieldsValue({
          profile_name: profile?.profile_name,
          llm: llmItem?.value || null,
          embedding_model: embeddingItem?.value || null,
          vector_store: vectorDbItem?.value || null,
          x2text: x2textItem?.value || null,
          chunk_size: profile?.chunk_size,
          chunk_overlap: profile?.chunk_overlap,
          similarity_top_k: profile?.similarity_top_k,
        });
      })
      .catch((err) => {
        handleException(err, "Failed to fetch profile data");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const handleSubmit = () => {
    form
      .validateFields()
      .then((values) => {
        setLoading(true);

        const payload = {
          profile_name: values.profile_name,
          lookup_project: projectId,
          llm: values.llm,
          embedding_model: values.embedding_model,
          vector_store: values.vector_store,
          x2text: values.x2text,
          chunk_size: values.chunk_size,
          chunk_overlap: values.chunk_overlap,
          similarity_top_k: values.similarity_top_k,
        };

        const requestOptions = {
          method: isEdit ? "PATCH" : "POST",
          url: isEdit
            ? `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/${profileId}/`
            : `/api/v1/unstract/${sessionDetails?.orgId}/lookup/lookup-profiles/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: payload,
        };

        axiosPrivate(requestOptions)
          .then(() => {
            setAlertDetails({
              type: "success",
              content: `Profile ${isEdit ? "updated" : "created"} successfully`,
            });
            onClose(true); // Close and refresh
          })
          .catch((err) => {
            handleException(
              err,
              `Failed to ${isEdit ? "update" : "create"} profile`
            );
          })
          .finally(() => {
            setLoading(false);
          });
      })
      .catch((info) => {
        console.log("Validation Failed:", info);
      });
  };

  return (
    <Modal
      title={modalTitle}
      open={true}
      onOk={handleSubmit}
      onCancel={() => onClose(false)}
      width={700}
      confirmLoading={loading}
      okText={isEdit ? "Update" : "Create"}
      cancelText="Cancel"
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          chunk_size: 1000,
          chunk_overlap: 200,
          similarity_top_k: 5,
        }}
      >
        <Form.Item
          label="Profile Name"
          name="profile_name"
          rules={[
            { required: true, message: "Please enter profile name" },
            { whitespace: true, message: "Profile name cannot be empty" },
          ]}
        >
          <Input placeholder="Enter profile name" />
        </Form.Item>

        <Typography.Text strong>Adapter Configuration</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="LLM"
                name="llm"
                rules={[{ required: true, message: "Please select an LLM" }]}
              >
                <Select
                  placeholder="Select LLM"
                  loading={adaptersLoading}
                  showSearch
                  optionFilterProp="label"
                >
                  {llmItems.map((item) => (
                    <Option
                      key={item.value}
                      value={item.value}
                      label={item.label}
                    >
                      {item.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label="Embedding Model"
                name="embedding_model"
                rules={[
                  {
                    required: true,
                    message: "Please select an embedding model",
                  },
                ]}
              >
                <Select
                  placeholder="Select embedding model"
                  loading={adaptersLoading}
                  showSearch
                  optionFilterProp="label"
                >
                  {embeddingItems.map((item) => (
                    <Option
                      key={item.value}
                      value={item.value}
                      label={item.label}
                    >
                      {item.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="Vector Database"
                name="vector_store"
                rules={[
                  {
                    required: true,
                    message: "Please select a vector database",
                  },
                ]}
              >
                <Select
                  placeholder="Select vector database"
                  loading={adaptersLoading}
                  showSearch
                  optionFilterProp="label"
                >
                  {vectorDbItems.map((item) => (
                    <Option
                      key={item.value}
                      value={item.value}
                      label={item.label}
                    >
                      {item.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label="Text Extractor"
                name="x2text"
                rules={[
                  { required: true, message: "Please select a text extractor" },
                ]}
              >
                <Select
                  placeholder="Select text extractor"
                  loading={adaptersLoading}
                  showSearch
                  optionFilterProp="label"
                >
                  {x2TextItems.map((item) => (
                    <Option
                      key={item.value}
                      value={item.value}
                      label={item.label}
                    >
                      {item.label}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
        </div>

        <Typography.Text strong>Chunking Configuration</Typography.Text>
        <div style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label="Chunk Size"
                name="chunk_size"
                rules={[
                  { required: true, message: "Please enter chunk size" },
                  {
                    type: "number",
                    min: 0,
                    max: 10000,
                    message:
                      "Chunk size must be between 0 and 10000 (0 = full context mode)",
                  },
                ]}
                tooltip="Set to 0 to use full context mode (no chunking)"
              >
                <InputNumber
                  style={{ width: "100%" }}
                  placeholder="1000"
                  min={0}
                  max={10000}
                />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label="Chunk Overlap"
                name="chunk_overlap"
                rules={[
                  { required: true, message: "Please enter chunk overlap" },
                  {
                    type: "number",
                    min: 0,
                    max: 1000,
                    message: "Chunk overlap must be between 0 and 1000",
                  },
                ]}
              >
                <InputNumber
                  style={{ width: "100%" }}
                  placeholder="200"
                  min={0}
                  max={1000}
                />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label="Similarity Top K"
                name="similarity_top_k"
                rules={[
                  { required: true, message: "Please enter similarity top k" },
                  {
                    type: "number",
                    min: 1,
                    max: 20,
                    message: "Similarity top k must be between 1 and 20",
                  },
                ]}
              >
                <InputNumber
                  style={{ width: "100%" }}
                  placeholder="5"
                  min={1}
                  max={20}
                />
              </Form.Item>
            </Col>
          </Row>
        </div>
      </Form>
    </Modal>
  );
}

ProfileFormModal.propTypes = {
  projectId: PropTypes.string.isRequired,
  profileId: PropTypes.string,
  onClose: PropTypes.func.isRequired,
};

export { ProfileFormModal };
