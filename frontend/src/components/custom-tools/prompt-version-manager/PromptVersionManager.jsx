import { useState } from "react";
import {
  CloseOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Modal,
  Button,
  Row,
  Col,
  Tag,
  Divider,
  Tooltip,
  Space,
  Typography,
} from "antd";
import PropTypes from "prop-types";

import "./PromptVersionManager.css";

import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCustomToolStore } from "../../../store/custom-tool-store";

const PromptVersionManager = ({ promptDetails, handleChange }) => {
  const [open, setOpen] = useState(false);
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const [isLoadingGetPromptVersions, setIsLoadingGetPromptVersions] =
    useState(false);
  const [isLoadingLoadPromptVersion, setIsLoadingLoadPromptVersion] =
    useState(false);
  const { details, updateCustomTool } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const [promptVersions, setPromptVersions] = useState([]);
  const getPromptVersions = (e) => {
    e.preventDefault();
    setIsLoadingGetPromptVersions(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-version-manager/${promptDetails?.prompt_id}/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setPromptVersions(data);
        setTooltipOpen(false);
        setOpen(true);
      })
      .catch((err) => {
        console.log(err);
        const content =
          err?.data?.errors?.[0]?.detail || "Failed to get prompt versions";
        setAlertDetails({
          type: "error",
          content,
        });
      })
      .finally(() => {
        setIsLoadingGetPromptVersions(false);
      });
  };

  const loadPromptVersion = (promptVersion) => {
    if (promptDetails?.loaded_version === promptVersion) {
      return;
    }
    setIsLoadingLoadPromptVersion(true);
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-version-manager/${promptDetails?.prompt_id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
      },
      data: {
        prompt_version: promptVersion,
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        const modifiedDetails = { ...details };
        const modifiedPrompts = [...(modifiedDetails?.prompts || [])].map(
          (item) => {
            if (item?.prompt_id === promptDetails?.prompt_id) {
              return data?.loaded_data;
            }
            return item;
          }
        );
        modifiedDetails["prompts"] = modifiedPrompts;
        updateCustomTool({ details: modifiedDetails });
        setAlertDetails({
          type: "success",
          content:
            data?.message ||
            `Loaded prompt version '${promptVersion}' successfully`,
        });
        setOpen(false);
      })
      .catch((err) => {
        console.log(err);
        const content =
          err?.response.data?.["prompt_version"] ||
          `Failed to load prompt version '${promptVersion}'`;
        setAlertDetails({
          type: "error",
          content,
        });
      })
      .finally(() => {
        setIsLoadingLoadPromptVersion(false);
      });
  };

  return (
    <>
      <Tooltip title="Prompt Version" open={tooltipOpen} destroyTooltipOnHide>
        <Tag
          color={promptDetails?.loaded_version_id ? "blue" : "warning"}
          className={`prompt_version_tag ${
            promptDetails?.loaded_version_id ? "" : "warning"
          }`}
          onClick={getPromptVersions}
          onMouseEnter={() => setTooltipOpen(true)}
          onMouseLeave={() => setTooltipOpen(false)}
          icon={isLoadingGetPromptVersions ? <LoadingOutlined /> : null}
        >
          {promptDetails?.loaded_version}
        </Tag>
      </Tooltip>
      <Modal
        title={
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Typography.Title level={5} className="m0">
              Prompt Version Manager
            </Typography.Title>
            <Space>
              {!promptDetails?.loaded_version_id && (
                <Tag icon={<ExclamationCircleOutlined />} color="warning">
                  Version {promptDetails?.loaded_version} will be created if the
                  prompt is ran
                </Tag>
              )}
              <Button
                type="text"
                icon={<CloseOutlined style={{ color: "#00000073" }} />}
                onClick={() => setOpen(false)}
              />
            </Space>
          </div>
        }
        open={open}
        closable={false}
        footer={null}
        width={800}
        destroyOnClose
        centered
      >
        <Divider />
        {promptVersions.map((promptVersion) => (
          <div key={promptVersion?.id} style={{ margin: 16 }}>
            <Row gutter={16} align="middle">
              <Col
                span={2}
                style={{
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                <Tag color="blue">{promptVersion?.version}</Tag>
              </Col>
              <Col span={18}>
                <Row>
                  <Typography.Text strong>
                    {promptVersion?.prompt_key}
                  </Typography.Text>
                </Row>
                <Row>
                  <Typography.Paragraph
                    style={{ whiteSpace: "pre-wrap" }}
                    ellipsis={{
                      rows: 2,
                      expandable: true,
                      symbol: "more",
                    }}
                    copyable
                  >
                    {promptVersion?.prompt}
                  </Typography.Paragraph>
                </Row>
                <Row
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <Space>
                    <Tag color="magenta">
                      {promptVersion?.profile_manager?.llm}
                    </Tag>
                    <Tag color="gold">
                      {promptVersion?.profile_manager?.embedding_model}
                    </Tag>
                    <Tag color="blue">
                      {promptVersion?.profile_manager?.vector_store}
                    </Tag>
                    <Tag color="green">
                      {promptVersion?.profile_manager?.x2text}
                    </Tag>
                  </Space>
                  <div>Type: {promptVersion?.enforce_type}</div>
                </Row>
              </Col>
              <Col
                span={4}
                style={{
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                <Tooltip
                  title={
                    promptDetails?.loaded_version === promptVersion?.version
                      ? "Currently Loaded"
                      : "Load"
                  }
                >
                  <Button
                    type="text"
                    icon={<UploadOutlined rotate={180} />}
                    onClick={() => loadPromptVersion(promptVersion?.version)}
                    loading={isLoadingLoadPromptVersion}
                    disabled={
                      promptDetails?.loaded_version === promptVersion?.version
                    }
                  />
                </Tooltip>
                {/* <Space>
                  <Tooltip title="Load">
                    <Button
                      type="text"
                      icon={<UploadOutlined rotate={180} />}
                      onClick={() => {}}
                    />
                  </Tooltip>
                  <Tooltip title="Delete">
                    <Button
                      type="text"
                      icon={<DeleteOutlined />}
                      onClick={() => {}}
                    />
                  </Tooltip>
                </Space> */}
              </Col>
            </Row>
            <Divider />
          </div>
        ))}
      </Modal>
    </>
  );
};

PromptVersionManager.propTypes = {
  promptDetails: PropTypes.object.isRequired,
  handleChange: PropTypes.func.isRequired,
};

export { PromptVersionManager };
