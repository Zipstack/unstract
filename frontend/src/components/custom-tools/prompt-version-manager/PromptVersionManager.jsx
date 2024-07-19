import { useEffect, useState } from "react";
import {
  DeleteOutlined,
  DeleteTwoTone,
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

const PromptVersionManager = ({ promptDetails, handleChange }) => {
  const [open, setOpen] = useState(false);
  const [isLoadingGetPromptVersions, setIsLoadingGetPromptVersions] =
    useState(false);
  const [isLoadingLoadPromptVersion, setIsLoadingLoadPromptVersion] =
    useState(false);
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
        // setPromptVersions(data);
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
      <Tooltip title="Prompt Version">
        <Tag
          className="no-outline"
          color="blue"
          style={{
            cursor: "pointer",
            fontWeight: "bold",
            transition: "border 0.3s ease",
            outline: "none",
          }}
          onMouseEnter={(e) => {
            e.target.style.border = "1px solid #1890ff";
          }} // Increase border on hover
          onMouseLeave={(e) => {
            e.target.style.border = "1px solid #91caff";
          }} // Restore initial border
          // onClick={() => console.log("CLICK")}
          onClick={getPromptVersions}
          icon={isLoadingGetPromptVersions ? <LoadingOutlined /> : <></>}
        >
          {promptDetails?.loaded_version}
        </Tag>
      </Tooltip>
      <Modal
        title="Prompt Version Manager"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={800}
        destroyOnClose
        centered
      >
        <Divider />
        {promptVersions.map((promptVersion) => (
          <div
            key={promptVersion?.prompt_version_manager_id}
            style={{ margin: 16 }}
          >
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
