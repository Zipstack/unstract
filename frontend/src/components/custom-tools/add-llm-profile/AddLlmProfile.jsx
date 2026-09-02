import { ArrowLeft, ChevronDown, ChevronRight, Settings } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Form } from "@/components/ui/shims/antd-form";
import { Input, Select } from "@/components/ui/shims/antd-inputs";
import { Col, Row, Space } from "@/components/ui/shims/antd-layout";
import { Collapse } from "@/components/ui/shims/antd-overlays";
import { Typography } from "@/components/ui/shims/antd-typography";
import { cn } from "@/lib/utils";

import { getBackendErrorDetail } from "../../../helpers/GetStaticData";
import { fetchAllPages } from "../../../helpers/pagination";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CustomButton } from "../../widgets/custom-button/CustomButton";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./AddLlmProfile.css";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useRetrievalStrategies } from "../../../hooks/useRetrievalStrategies";
import RetrievalStrategyModal from "../retrieval-strategy-modal/RetrievalStrategyModal";

function AddLlmProfile({
  editLlmProfileId,
  setEditLlmProfileId,
  setIsAddLlm,
  handleDefaultLlm,
}) {
  const [form] = Form.useForm();
  const [formDetails, setFormDetails] = useState({});
  const [resetForm, setResetForm] = useState(false);
  const [backendErrors, setBackendErrors] = useState(null);
  const [retrievalItems, setRetrievalItems] = useState([]);
  const [hasLoadedFromApi, setHasLoadedFromApi] = useState(false);
  const [llmItems, setLlmItems] = useState([]);
  const [vectorDbItems, setVectorDbItems] = useState([]);
  const [embeddingItems, setEmbeddingItems] = useState([]);
  const [x2TextItems, setX2TextItems] = useState([]);
  const [activeKey, setActiveKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [modalTitle, setModalTitle] = useState("");
  const [areAdaptersReady, setAreAdaptersReady] = useState(false);
  const [isRetrievalModalVisible, setIsRetrievalModalVisible] = useState(false);
  const { sessionDetails } = useSessionStore();
  const { details, llmProfiles, updateCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  // P4: antd's theme token replaced by the Midnight Bloom CSS variable.
  const token = { colorBgContainer: "var(--card)" };
  const handleException = useExceptionHandler();
  const { setPostHogCustomEvent } = usePostHogEvents();
  const { getStrategies } = useRetrievalStrategies();

  const editedProfile = llmProfiles?.find(
    (item) => item?.profile_id === editLlmProfileId,
  );

  const adapterOptions = (items, field) => {
    const id = editedProfile?.[`${field}_id`];
    if (!id || items?.some((item) => item?.value === id)) {
      return items;
    }
    return [
      ...items,
      { value: id, label: editedProfile?.[field], disabled: true },
    ];
  };

  useEffect(() => {
    setAdaptorProfilesDropdown();
  }, []);

  // Load retrieval strategies when tool_id is available (only once)
  useEffect(() => {
    if (details?.tool_id && !hasLoadedFromApi) {
      const loadStrategies = async () => {
        try {
          const strategies = await getStrategies(details.tool_id);
          const items =
            strategies?.map((strategy) => ({
              value: strategy?.key,
              label: strategy?.title,
            })) || [];
          setRetrievalItems(items);
          setHasLoadedFromApi(true);
        } catch (error) {
          console.error("Error loading retrieval strategies:", error);
          setHasLoadedFromApi(true);
        }
      };

      loadStrategies();
    }
  }, [details?.tool_id, hasLoadedFromApi]); // getStrategies intentionally omitted to prevent infinite re-renders

  useEffect(() => {
    if (editLlmProfileId) {
      return;
    }

    setResetForm(true);
    setFormDetails({
      profile_name: "",
      llm: "",
      chunk_size: 0,
      vector_store: "",
      chunk_overlap: 0,
      embedding_model: "",
      x2text: "",
      retrieval_strategy: "simple",
      similarity_top_k: 3,
      section: "Default",
      prompt_studio_tool: details?.tool_id,
    });

    setModalTitle("Add New LLM Profile");
    setActiveKey(false);
  }, []);

  useEffect(() => {
    if (!editLlmProfileId || !areAdaptersReady) {
      return;
    }

    setModalTitle("Edit LLM Profile");

    setResetForm(true);
    setFormDetails({
      profile_name: editedProfile?.profile_name,
      llm: editedProfile?.llm_id || null,
      chunk_size: editedProfile?.chunk_size,
      vector_store: editedProfile?.vector_store_id || null,
      chunk_overlap: editedProfile?.chunk_overlap,
      embedding_model: editedProfile?.embedding_model_id || null,
      x2text: editedProfile?.x2text_id || null,
      retrieval_strategy: editedProfile?.retrieval_strategy,
      similarity_top_k: editedProfile?.similarity_top_k,
      section: editedProfile?.section,
      prompt_studio_tool: details?.tool_id,
    });
    setActiveKey(true);
  }, [editLlmProfileId, areAdaptersReady]);

  useEffect(() => {
    if (resetForm) {
      form.setFieldsValue(formDetails);
      setResetForm(false);
    }
  }, [formDetails]);

  const [tokenSize, setTokenSize] = useState(0);
  const [maxTokenSize, setMaxTokenSize] = useState(0);

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
          (error) => error.attr !== changedFieldName,
        );
        return { ...prevErrors, errors: updatedErrors };
      }
      return null;
    });
  };

  const setAdaptorProfilesDropdown = () => {
    fetchAllPages(axiosPrivate, {
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/`,
    })
      .then((data) => {
        const llm = [];
        const vectorDb = [];
        const embedding = [];
        const x2Text = [];

        data.forEach((item) => {
          const option = { value: item?.id, label: item?.adapter_name };
          if (item?.adapter_type === "LLM") {
            llm.push(option);
          } else if (item?.adapter_type === "VECTOR_DB") {
            vectorDb.push(option);
          } else if (item?.adapter_type === "EMBEDDING") {
            embedding.push(option);
          } else if (item?.adapter_type === "X2TEXT") {
            x2Text.push(option);
          }
        });

        setLlmItems(llm);
        setVectorDbItems(vectorDb);
        setEmbeddingItems(embedding);
        setX2TextItems(x2Text);
        setAreAdaptersReady(true);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(
            err,
            "Failed to get the dropdown list for LLM Adapters",
          ),
        );
      });
  };

  const getItems = () => [
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
            <button
              type="button"
              className="retrieval-strategy-selector"
              onClick={handleRetrievalModalOpen}
              aria-label="Select retrieval strategy"
              aria-expanded={isRetrievalModalVisible}
              aria-haspopup="dialog"
            >
              <span
                className={`retrieval-strategy-text ${
                  formDetails.retrieval_strategy
                    ? "retrieval-strategy-text--selected"
                    : "retrieval-strategy-text--placeholder"
                }`}
              >
                {formDetails.retrieval_strategy
                  ? retrievalItems.find(
                      (item) => item.value === formDetails.retrieval_strategy,
                    )?.label || "Select retrieval strategy"
                  : "Select retrieval strategy"}
              </span>
              <div className="retrieval-strategy-actions">
                <Settings
                  className="retrieval-strategy-settings-icon"
                  title="Configure retrieval strategy"
                />
                <ChevronDown className="retrieval-strategy-dropdown-icon" />
              </div>
            </button>
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
        </div>
      ),
    },
  ];

  const handleSubmit = () => {
    setLoading(true);
    let method = "POST";
    let url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/profilemanager/${details?.tool_id}`;

    if (editLlmProfileId?.length) {
      method = "PUT";
      url = `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/profile-manager/`;
      url += `${editLlmProfileId}/`;
    } else {
      try {
        setPostHogCustomEvent("intent_success_ps_new_llm_profile", {
          info: "Clicked on 'Add' button",
        });
      } catch (_err) {
        // If an error occurs while setting custom posthog event, ignore it and continue
      }
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
            item?.profile_id === editLlmProfileId ? data : item,
          );
        } else {
          newLlmProfiles.push(data);
        }
        const updatedState = {
          llmProfiles: newLlmProfiles,
        };
        updateCustomTool(updatedState);
        setAlertDetails({
          type: "success",
          content: "Saved successfully",
        });

        if (newLlmProfiles?.length === 1) {
          // Set the first LLM profile as default
          handleDefaultLlm(data?.profile_id);
        }
        setIsAddLlm(false);
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "", setBackendErrors));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  const handleCollapse = (keys) => {
    setActiveKey(!!keys?.length);
  };

  const handleCaretIcon = (isActive) => {
    // `rotate` was an antd icon-font prop; lucide ships SVGs and ignores it, so
    // the caret stayed pointing right and the panel read as collapsed while
    // open. Tailwind's transform does what the prop used to.
    return (
      <ChevronRight
        className={cn("transition-transform", isActive && "rotate-90")}
      />
    );
  };

  const handleLlmChangeForTokens = async (value) => {
    if (!value) {
      return null;
    }
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/adapter/info/${value}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const contextWindowSize = data.context_window_size;
        const chunkSize = form.getFieldValue("chunk_size");
        setTokenSize(chunkSize > 0 ? calcTokenSize(chunkSize) : 0);
        setMaxTokenSize(contextWindowSize);
      })
      .catch((err) => {
        setAlertDetails(
          handleException(
            err,
            "Failed to get chunk size information for the requested LLM. Please proceed with a sane default.",
          ),
        );
      });
  };

  const handleChunkSizeChange = async (event) => {
    const value = event.target.value;
    const tokenSize = calcTokenSize(value);
    setTokenSize(tokenSize);
  };

  function calcTokenSize(chunkSize) {
    const tokenSize = (chunkSize / 4 / 1024).toFixed(1);
    return tokenSize;
  }

  const handleRetrievalModalOpen = () => {
    setIsRetrievalModalVisible(true);
  };

  const handleRetrievalStrategySelect = (strategy) => {
    const strategyLabel =
      retrievalItems.find((item) => item.value === strategy)?.label || strategy;
    form.setFieldsValue({ retrieval_strategy: strategy });
    setFormDetails({ ...formDetails, retrieval_strategy: strategy });
    setIsRetrievalModalVisible(false);

    // Clear any existing backend errors for this field
    setBackendErrors((prevErrors) => {
      if (prevErrors) {
        const updatedErrors = prevErrors.errors.filter(
          (error) => error.attr !== "retrieval_strategy",
        );
        return { ...prevErrors, errors: updatedErrors };
      }
      return null;
    });

    setAlertDetails({
      type: "success",
      content: `Retrieval strategy set to: ${strategyLabel}`,
    });
  };

  return (
    <div className="add-llm-profile-body">
      <Form
        form={form}
        layout="vertical"
        initialValues={formDetails}
        onValuesChange={handleInputChange}
        onFinish={handleSubmit}
      >
        <SpaceWrapper>
          <div>
            <Button size="small" type="text" onClick={() => setIsAddLlm(false)}>
              <ArrowLeft />
            </Button>
            <Typography.Text className="add-cus-tool-header">
              {modalTitle}
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
                  <Select
                    showSearch
                    options={adapterOptions(llmItems, "llm")}
                    onSelect={handleLlmChangeForTokens}
                  />
                </Form.Item>
              </Col>
              <Col span={1} />
              <Col span={8}>
                <Form.Item
                  label={
                    <>
                      Chunk Size
                      <Typography.Text type="secondary">
                        {" "}
                        (Set to 0 if documents are small)
                      </Typography.Text>
                    </>
                  }
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
                  extra={`~= ${tokenSize}k tokens, Max: ${maxTokenSize}`}
                >
                  <Input type="number" onChange={handleChunkSizeChange} />
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
                  <Select
                    showSearch
                    options={adapterOptions(vectorDbItems, "vector_store")}
                  />
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
              <Select
                showSearch
                options={adapterOptions(embeddingItems, "embedding_model")}
              />
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
              <Select
                showSearch
                options={adapterOptions(x2TextItems, "x2text")}
              />
            </Form.Item>
            <Collapse
              className="add-llm-profile-advanced"
              expandIcon={({ isActive }) => handleCaretIcon(isActive)}
              size="small"
              style={{
                background: token.colorBgContainer,
              }}
              items={getItems()}
              activeKey={activeKey && "1"}
              onChange={handleCollapse}
            />
          </div>
        </SpaceWrapper>
        <Form.Item
          className="display-flex-right add-llm-profile-footer"
          style={{ backgroundColor: token.colorBgContainer }}
        >
          <Space>
            <CustomButton type="primary" htmlType="submit" loading={loading}>
              {editLlmProfileId ? "Update" : "Add"}
            </CustomButton>
          </Space>
        </Form.Item>
      </Form>

      <RetrievalStrategyModal
        visible={isRetrievalModalVisible}
        onCancel={() => setIsRetrievalModalVisible(false)}
        onOk={handleRetrievalStrategySelect}
        currentStrategy={formDetails.retrieval_strategy}
        loading={false}
      />
    </div>
  );
}

AddLlmProfile.propTypes = {
  editLlmProfileId: PropTypes.string,
  setEditLlmProfileId: PropTypes.func.isRequired,
  setIsAddLlm: PropTypes.func.isRequired,
  handleDefaultLlm: PropTypes.func.isRequired,
};

export { AddLlmProfile };
