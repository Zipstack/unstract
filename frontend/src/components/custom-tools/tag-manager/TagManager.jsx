import { useState } from "react";
import { Modal, Table, Tag, Space } from "antd";
import PropTypes from "prop-types";

const TagManagerModal = ({ open, onClose }) => {
  const [data] = useState([
    {
      key: "1",
      tag: { name: "Important", color: "red" },
      lastSaved: "2024-03-25T08:00:00Z", // Example timestamp
    },
    {
      key: "2",
      tag: { name: "Work", color: "blue" },
      lastSaved: "2024-07-13T16:15:00Z", // Example timestamp
    },
    // Add more rows as needed
  ]);

  const columns = [
    {
      title: "Tag",
      dataIndex: "tag",
      key: "tag",
      render: (tag) => <Tag color={tag.color}>{tag.name}</Tag>,
    },
    {
      title: "Last Saved",
      dataIndex: "lastSaved",
      key: "lastSaved",
      render: (lastSaved) => {
        const date = new Date(lastSaved);
        const options = { month: "long", day: "numeric", year: "numeric" };
        const formattedDate = date.toLocaleDateString("en-US", options);

        // Add suffix for day (e.g., 1st, 2nd, 3rd, 4th)
        const day = date.getDate();
        const suffix =
          day === 1 ? "st" : day === 2 ? "nd" : day === 3 ? "rd" : "th";
        return `${formattedDate}${suffix}, ${date.getFullYear()}`;
      },
    },
    {
      title: "Actions",
      key: "actions",
      render: () => (
        <Space size="middle">
          <a>Load</a>
          <a>Delete</a>
        </Space>
      ),
    },
  ];

  return (
    <Modal open={open} title="Tag Data" onCancel={onClose} footer={null}>
      <Table columns={columns} dataSource={data} />
    </Modal>
  );
};
TagManagerModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};
export { TagManagerModal };
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

import "./PromptVersionModal.css";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";

const TagManager = ({ promptDetails }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [viewMoreVisible, setViewMoreVisible] = useState(false);
  const [fullPromptText, setFullPromptText] = useState("");
  const { setAlertDetails } = useAlertStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const [promptVersions, setPromptVersions] = useState([]);
  const [count, setCount] = useState(0);
  const [next, setNext] = useState(null);
  const [previous, setPrevious] = useState(null);

  useEffect(() => {
    console.log("IT SHOULD BE HERE");
    console.log(promptDetails);
  }, []);

  const getPromptVersions = (e) => {
    e.preventDefault();
    setLoading(true);
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/prompt-version-manager/${promptDetails?.prompt_id}/`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        const data = res?.data;
        setPromptVersions(data?.results);
        setCount(data?.count);
        setNext(data?.next);
        setPrevious(data?.previous);
        setOpen(true);
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Failed to fetch prompt versions",
        });
      })
      .finally(() => {
        setLoading(false);
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
          icon={loading ? <LoadingOutlined /> : <></>}
        >
          {promptDetails?.loaded_version}
        </Tag>
      </Tooltip>
      <Modal
        title="Prompt Version Manager"
        open={open}
        onOk={() => setOpen(false)}
        onCancel={() => setOpen(false)}
        width={800}
        destroyOnClose
      >
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
                <Space>
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
                </Space>
              </Col>
            </Row>
            <Divider />
          </div>
        ))}
      </Modal>
    </>
  );
};

PromptVersionModal.propTypes = {
  promptDetails: PropTypes.object.isRequired,
};

export { PromptVersionModal };
