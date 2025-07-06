import { Modal, Form, Select, Typography, Space, Divider } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import "./AdapterSelectionModal.css";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

const { Text, Title } = Typography;
const { Option } = Select;

function AdapterSelectionModal({
  open,
  setOpen,
  onConfirm,
  loading,
  projectData,
}) {
  const [form] = Form.useForm();
  const [adapters, setAdapters] = useState({
    llm: [],
    embedding: [],
    vectorDb: [],
    x2text: [],
  });
  const [loadingAdapters, setLoadingAdapters] = useState(false);

  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (open) {
      fetchAdapters();
    }
  }, [open]);

  const fetchAdapters = async () => {
    setLoadingAdapters(true);

    try {
      const adapterTypes = ["LLM", "EMBEDDING", "VECTOR_DB", "X2TEXT"];
      const requests = adapterTypes.map((type) =>
        axiosPrivate({
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
          },
          params: {
            adapter_type: type,
          },
        })
      );

      const responses = await Promise.all(requests);

      setAdapters({
        llm: responses[0]?.data || [],
        embedding: responses[1]?.data || [],
        vectorDb: responses[2]?.data || [],
        x2text: responses[3]?.data || [],
      });
    } catch (err) {
      setAlertDetails(
        handleException(err, "Failed to fetch available adapters")
      );
    } finally {
      setLoadingAdapters(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setOpen(false);
  };

  const handleOk = () => {
    form.validateFields().then((values) => {
      onConfirm({
        selectedAdapters: values,
        projectData,
      });
      setOpen(false);
    });
  };

  const validateAdapter = (_, value) => {
    if (!value) {
      return Promise.reject(new Error("Please select an adapter"));
    }
    return Promise.resolve();
  };

  return (
    <Modal
      title="Select Adapters for Import"
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      okText="Import Project"
      cancelText="Cancel"
      width={700}
      maskClosable={false}
    >
      <div className="adapter-selection-modal__description">
        <Text type="secondary">
          This project requires the following adapters to function properly.
          Please select the appropriate adapters from your available options.
        </Text>
      </div>

      <Form form={form} layout="vertical" disabled={loadingAdapters}>
        <Title level={5}>Required Adapters</Title>

        <Form.Item
          label="LLM (Large Language Model)"
          name="llm"
          rules={[{ validator: validateAdapter }]}
          extra="Select the LLM adapter for processing prompts and generating responses"
        >
          <Select
            placeholder="Select an LLM adapter"
            loading={loadingAdapters}
            showSearch
            filterOption={(input, option) =>
              option.children.toLowerCase().includes(input.toLowerCase())
            }
          >
            {adapters.llm.map((adapter) => (
              <Option key={adapter?.id} value={adapter?.id}>
                <Space>
                  <span>{adapter?.adapter_name}</span>
                  <Text
                    type="secondary"
                    className="adapter-selection-modal__adapter-id"
                  >
                    ({adapter?.adapter_id})
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="Vector Database"
          name="vectorDb"
          rules={[{ validator: validateAdapter }]}
          extra="Select the vector database for storing and retrieving document embeddings"
        >
          <Select
            placeholder="Select a vector database adapter"
            loading={loadingAdapters}
            showSearch
            filterOption={(input, option) =>
              option.children.toLowerCase().includes(input.toLowerCase())
            }
          >
            {adapters?.vectorDb?.map((adapter) => (
              <Option key={adapter?.id} value={adapter?.id}>
                <Space>
                  <span>{adapter?.adapter_name}</span>
                  <Text
                    type="secondary"
                    className="adapter-selection-modal__adapter-id"
                  >
                    ({adapter?.adapter_id})
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="Embedding Model"
          name="embedding"
          rules={[{ validator: validateAdapter }]}
          extra="Select the embedding model for converting text to vector representations"
        >
          <Select
            placeholder="Select an embedding adapter"
            loading={loadingAdapters}
            showSearch
            filterOption={(input, option) =>
              option.children.toLowerCase().includes(input.toLowerCase())
            }
          >
            {adapters?.embedding?.map((adapter) => (
              <Option key={adapter?.id} value={adapter?.id}>
                <Space>
                  <span>{adapter?.adapter_name}</span>
                  <Text
                    type="secondary"
                    className="adapter-selection-modal__adapter-id"
                  >
                    ({adapter?.adapter_id})
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item
          label="X2Text Adapter"
          name="x2text"
          rules={[{ validator: validateAdapter }]}
          extra="Select the text extraction adapter for processing different file formats"
        >
          <Select
            placeholder="Select an X2Text adapter"
            loading={loadingAdapters}
            showSearch
            filterOption={(input, option) =>
              option.children.toLowerCase().includes(input.toLowerCase())
            }
          >
            {adapters?.x2text?.map((adapter) => (
              <Option key={adapter?.id} value={adapter?.id}>
                <Space>
                  <span>{adapter?.adapter_name}</span>
                  <Text
                    type="secondary"
                    className="adapter-selection-modal__adapter-id"
                  >
                    ({adapter?.adapter_id})
                  </Text>
                </Space>
              </Option>
            ))}
          </Select>
        </Form.Item>

        <Divider />

        <Text type="secondary" className="adapter-selection-modal__note">
          Note: These adapters will be used to create the LLM Profile for the
          imported project. You can modify these settings later in the
          project&apos;s profile configuration.
        </Text>
      </Form>
    </Modal>
  );
}

AdapterSelectionModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
  loading: PropTypes.bool.isRequired,
  projectData: PropTypes.object,
};

export { AdapterSelectionModal };
