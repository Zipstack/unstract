import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Modal, Table, Button, Tag, Spin, Space, message } from "antd";
import {
  HistoryOutlined,
  SwapOutlined,
  LoadingOutlined,
} from "@ant-design/icons";

import { useMockApi } from "../hooks/useMockApi";
import { formatDate, formatAccuracy } from "../utils/helpers";

const PromptHistoryModal = ({
  visible,
  onClose,
  projectId,
  currentVersion,
  hasUnsavedChanges,
  onLoadVersion,
  onCompare,
}) => {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(false);
  const { getPrompts } = useMockApi();

  // Fetch prompts when modal opens
  useEffect(() => {
    if (visible && projectId) {
      fetchPrompts();
    }
  }, [visible, projectId]);

  const fetchPrompts = async () => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      const data = await getPrompts(projectId);
      setPrompts(data);
    } catch (error) {
      message.error("Failed to load prompt history");
      console.error("Fetch prompts error:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadVersion = (version) => {
    if (hasUnsavedChanges) {
      Modal.confirm({
        title: "Unsaved Changes",
        content:
          "You have unsaved changes. Loading a different version will discard them. Continue?",
        okText: "Yes, Load Version",
        okType: "danger",
        onOk: () => {
          onLoadVersion(version);
          onClose();
        },
      });
    } else {
      onLoadVersion(version);
      onClose();
    }
  };

  const handleCompare = (version) => {
    onCompare(version);
    onClose();
  };

  const columns = [
    {
      title: "Version",
      dataIndex: "version",
      key: "version",
      width: 120,
      render: (version) => (
        <div>
          <span style={{ fontFamily: "monospace", fontSize: "13px" }}>
            v{version}
          </span>
          {version === currentVersion && (
            <Tag color="blue" style={{ marginLeft: "8px" }}>
              Current
            </Tag>
          )}
        </div>
      ),
    },
    {
      title: "Short Description",
      dataIndex: "short_desc",
      key: "short_desc",
      ellipsis: true,
      render: (text) => text || "-",
    },
    {
      title: "Long Description",
      dataIndex: "long_desc",
      key: "long_desc",
      ellipsis: true,
      render: (text) => text || "-",
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      width: 150,
      render: (date) => formatDate(date),
    },
    {
      title: "Accuracy",
      dataIndex: "accuracy",
      key: "accuracy",
      width: 100,
      render: (accuracy) => formatAccuracy(accuracy),
    },
    {
      title: "Actions",
      key: "actions",
      width: 120,
      align: "right",
      render: (_, record) => (
        <Space size="small">
          <Button
            type="primary"
            size="small"
            onClick={() => handleLoadVersion(record.version)}
            disabled={record.version === currentVersion}
          >
            Load
          </Button>
          <Button
            size="small"
            icon={<SwapOutlined />}
            onClick={() => handleCompare(record.version)}
            title="Compare with current"
          />
        </Space>
      ),
    },
  ];

  return (
    <Modal
      title={
        <span>
          <HistoryOutlined style={{ marginRight: "8px" }} />
          Prompt Version History
        </span>
      }
      open={visible}
      onCancel={onClose}
      footer={null}
      width={1000}
      destroyOnClose
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: "40px" }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          <p style={{ marginTop: "16px", color: "#666" }}>Loading history...</p>
        </div>
      ) : prompts.length === 0 ? (
        <p style={{ textAlign: "center", padding: "40px", color: "#666" }}>
          No prompt versions found
        </p>
      ) : (
        <Table
          columns={columns}
          dataSource={prompts}
          rowKey="id"
          pagination={false}
          size="small"
          rowClassName={(record) =>
            record.version === currentVersion ? "ant-table-row-selected" : ""
          }
        />
      )}
    </Modal>
  );
};

PromptHistoryModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  projectId: PropTypes.string.isRequired,
  currentVersion: PropTypes.number.isRequired,
  hasUnsavedChanges: PropTypes.bool,
  onLoadVersion: PropTypes.func.isRequired,
  onCompare: PropTypes.func.isRequired,
};

export default PromptHistoryModal;
