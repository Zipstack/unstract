import {
  ArrowLeftOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Select,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCopyToClipboard } from "../../../hooks/useCopyToClipboard";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
import { IslandLayout } from "../../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../../store/alert-store";
import { useSessionStore } from "../../../store/session-store";
import { ConfirmModal } from "../../widgets/confirm-modal/ConfirmModal.jsx";
import { SettingsLayout } from "../settings-layout/SettingsLayout.jsx";
import "../platform/PlatformSettings.css";
import "./GlobalApiDeploymentKeys.css";

const SAFE_TEXT_REGEX = /^[a-zA-Z0-9 \-_.,:'()/]+$/;
const SAFE_TEXT_MESSAGE =
  "Only alphanumeric characters, spaces, hyphens, underscores, periods, commas, colons, apostrophes, parentheses, and forward slashes are allowed.";

function DeploymentScopeFields({ form, deployments }) {
  const allowAll = Form.useWatch("allow_all_deployments", form);
  return (
    <>
      <Form.Item
        name="allow_all_deployments"
        valuePropName="checked"
        initialValue={false}
      >
        <Checkbox>Allow all API deployments</Checkbox>
      </Form.Item>
      <Form.Item
        name="api_deployments"
        label="Select API Deployments"
        rules={
          allowAll === false
            ? [{ required: true, message: "Select at least one deployment" }]
            : []
        }
      >
        <Select
          mode="multiple"
          placeholder="Search and select deployments"
          optionFilterProp="children"
          className="gadk__deployment-select"
          showSearch
          disabled={allowAll !== false}
        >
          {deployments?.map((d) => (
            <Select.Option key={d?.id} value={d?.id}>
              {d?.display_name || d?.api_name}
              {!d?.is_active && " (inactive)"}
            </Select.Option>
          ))}
        </Select>
      </Form.Item>
    </>
  );
}

DeploymentScopeFields.propTypes = {
  form: PropTypes.object.isRequired,
  deployments: PropTypes.array,
};

function GlobalApiDeploymentKeys() {
  const [keys, setKeys] = useState([]);
  const [deployments, setDeployments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [isSaving, setIsSaving] = useState(false);

  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const navigate = useNavigate();
  const handleException = useExceptionHandler();
  const copyToClipboard = useCopyToClipboard();

  const basePath = `/api/v1/unstract/${sessionDetails?.orgId}/global-api-deployment`;

  const fetchKeys = useCallback(() => {
    if (!sessionDetails?.orgId) {
      return;
    }
    setIsLoading(true);
    axiosPrivate({ method: "GET", url: `${basePath}/keys/` })
      .then((res) => setKeys(res?.data || []))
      .catch((err) =>
        setAlertDetails(
          handleException(err, "Failed to load Global API Deployment keys"),
        ),
      )
      .finally(() => setIsLoading(false));
  }, [basePath, sessionDetails?.orgId]);

  const fetchDeployments = useCallback(() => {
    if (!sessionDetails?.orgId) {
      return;
    }
    axiosPrivate({ method: "GET", url: `${basePath}/deployments/` })
      .then((res) => setDeployments(res?.data || []))
      .catch(() => {
        /* Silent fail - deployments list is non-critical */
      });
  }, [basePath, sessionDetails?.orgId]);

  useEffect(() => {
    fetchKeys();
    fetchDeployments();
  }, [fetchKeys, fetchDeployments]);

  const handleCreate = () => {
    createForm
      .validateFields()
      .then((values) => {
        setIsSaving(true);
        const payload = {
          ...values,
          allow_all_deployments: values?.allow_all_deployments ?? false,
          api_deployments:
            values?.allow_all_deployments === false
              ? values?.api_deployments || []
              : [],
        };
        axiosPrivate({
          method: "POST",
          url: `${basePath}/keys/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: payload,
        })
          .then((res) => {
            setIsCreateModalOpen(false);
            createForm.resetFields();
            fetchKeys();
            copyToClipboard(res?.data?.key, "API key");
          })
          .catch((err) =>
            setAlertDetails(handleException(err, "Failed to create key")),
          )
          .finally(() => setIsSaving(false));
      })
      .catch(() => {
        /* Invalid form: antd renders inline field errors; swallow the reject. */
      });
  };

  const handleEdit = () => {
    editForm
      .validateFields()
      .then((values) => {
        setIsSaving(true);
        const payload = {
          ...values,
          api_deployments:
            values?.allow_all_deployments === false
              ? values?.api_deployments || []
              : [],
        };
        axiosPrivate({
          method: "PATCH",
          url: `${basePath}/keys/${selectedKey?.id}/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: payload,
        })
          .then(() => {
            setIsEditModalOpen(false);
            editForm.resetFields();
            setSelectedKey(null);
            fetchKeys();
            setAlertDetails({
              type: "success",
              content: "Key updated successfully",
            });
          })
          .catch((err) =>
            setAlertDetails(handleException(err, "Failed to update key")),
          )
          .finally(() => setIsSaving(false));
      })
      .catch(() => {
        /* Invalid form: antd renders inline field errors; swallow the reject. */
      });
  };

  const handleToggleStatus = (record) => {
    axiosPrivate({
      method: "PATCH",
      url: `${basePath}/keys/${record?.id}/`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: { is_active: !record?.is_active },
    })
      .then(() => fetchKeys())
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to update key status")),
      );
  };

  const handleRotate = (record) => {
    axiosPrivate({
      method: "POST",
      url: `${basePath}/keys/${record?.id}/rotate/`,
      headers: { "X-CSRFToken": sessionDetails?.csrfToken },
    })
      .then((res) => {
        fetchKeys();
        copyToClipboard(res?.data?.key, "API key");
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to rotate key")),
      );
  };

  const handleDelete = (record) => {
    axiosPrivate({
      method: "DELETE",
      url: `${basePath}/keys/${record?.id}/`,
      headers: { "X-CSRFToken": sessionDetails?.csrfToken },
    })
      .then(() => {
        fetchKeys();
        setAlertDetails({
          type: "success",
          content: "Key deleted successfully",
        });
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to delete key")),
      );
  };

  const openEditModal = (record) => {
    setSelectedKey(record);
    editForm.setFieldsValue({
      description: record?.description,
      allow_all_deployments: record?.allow_all_deployments,
      api_deployments: record?.api_deployments?.map((d) => d?.id) || [],
    });
    setIsEditModalOpen(true);
  };

  const handleCopyKey = (record) => {
    axiosPrivate({ method: "GET", url: `${basePath}/keys/${record?.id}/` })
      .then((res) => copyToClipboard(res?.data?.key, "API key"))
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to copy key")),
      );
  };

  const formatDate = (dateStr) => {
    if (!dateStr) {
      return "";
    }
    return new Date(dateStr).toLocaleString();
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      width: "12%",
      ellipsis: true,
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      width: "14%",
      ellipsis: true,
    },
    {
      title: "API Key",
      dataIndex: "key",
      key: "key",
      width: "12%",
      render: (_, record) => (
        <Tooltip title="Click to copy">
          <Button
            type="text"
            className="gadk__key-cell"
            onClick={() => handleCopyKey(record)}
          >
            <Typography.Text className="gadk__key-text">
              {record?.key}
            </Typography.Text>
            <CopyOutlined className="gadk__copy-icon" />
          </Button>
        </Tooltip>
      ),
    },
    {
      title: "Scope",
      key: "scope",
      width: "16%",
      render: (_, record) =>
        record?.allow_all_deployments ? (
          <Tag color="blue">All Deployments</Tag>
        ) : (
          <Tooltip
            title={record?.api_deployments
              ?.map((d) => d?.display_name || d?.api_name)
              ?.join(", ")}
          >
            <Tag>{record?.api_deployments?.length || 0} deployment(s)</Tag>
          </Tooltip>
        ),
    },
    {
      title: "Active",
      dataIndex: "is_active",
      key: "is_active",
      width: "7%",
      render: (_, record) => (
        <Switch
          size="small"
          checked={record?.is_active}
          onChange={() => handleToggleStatus(record)}
        />
      ),
    },
    {
      title: "Created By",
      dataIndex: "created_by_email",
      key: "created_by_email",
      width: "14%",
      ellipsis: true,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      width: "12%",
      render: (text) => formatDate(text),
    },
    {
      title: "Actions",
      key: "actions",
      width: "13%",
      render: (_, record) => (
        <div className="gadk__actions">
          <ConfirmModal
            handleConfirm={() => handleRotate(record)}
            title="Rotate Key"
            content="This will generate a new key and invalidate the current one. Continue?"
            okText="Rotate"
          >
            <Tooltip title="Rotate key">
              <Button size="small" icon={<SyncOutlined />} />
            </Tooltip>
          </ConfirmModal>
          <Tooltip title="Edit">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
            />
          </Tooltip>
          <ConfirmModal
            handleConfirm={() => handleDelete(record)}
            title="Delete Key"
            content="Are you sure you want to delete this key? This action cannot be undone."
            okText="Delete"
          >
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </ConfirmModal>
        </div>
      ),
    },
  ];

  return (
    <SettingsLayout>
      <div>
        <div className="plt-set-head">
          <Button
            size="small"
            type="text"
            onClick={() =>
              navigate(`/${sessionDetails?.orgName}/settings/platform`)
            }
          >
            <ArrowLeftOutlined />
          </Button>
          <Typography.Text className="plt-set-head-typo">
            Global API Deployment Keys
          </Typography.Text>
        </div>
        <div className="plt-set-layout">
          <IslandLayout>
            <div className="gadk__content">
              <div className="gadk__header-actions">
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setIsCreateModalOpen(true)}
                >
                  New Key
                </Button>
              </div>
              <Table
                columns={columns}
                dataSource={keys}
                rowKey="id"
                loading={isLoading}
                pagination={false}
                size="small"
              />
            </div>
          </IslandLayout>
        </div>
      </div>

      {/* Create Modal */}
      <Modal
        title="Create Global API Deployment Key"
        open={isCreateModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setIsCreateModalOpen(false);
          createForm.resetFields();
        }}
        okText="Create"
        confirmLoading={isSaving}
        centered
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="name"
            label="Name"
            rules={[
              { required: true, message: "Name is required" },
              { max: 128, message: "Name cannot exceed 128 characters" },
              { pattern: SAFE_TEXT_REGEX, message: SAFE_TEXT_MESSAGE },
            ]}
          >
            <Input placeholder="Enter key name" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description"
            rules={[
              { required: true, message: "Description is required" },
              { max: 512, message: "Description cannot exceed 512 characters" },
              { pattern: SAFE_TEXT_REGEX, message: SAFE_TEXT_MESSAGE },
            ]}
          >
            <Input.TextArea
              placeholder="Enter description"
              rows={3}
              maxLength={512}
            />
          </Form.Item>
          <DeploymentScopeFields form={createForm} deployments={deployments} />
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title="Edit Global API Deployment Key"
        open={isEditModalOpen}
        onOk={handleEdit}
        onCancel={() => {
          setIsEditModalOpen(false);
          editForm.resetFields();
          setSelectedKey(null);
        }}
        okText="Save"
        confirmLoading={isSaving}
        centered
      >
        <Form form={editForm} layout="vertical">
          <Form.Item label="Name">
            <Input value={selectedKey?.name} disabled />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description"
            rules={[
              { required: true, message: "Description is required" },
              { max: 512, message: "Description cannot exceed 512 characters" },
              { pattern: SAFE_TEXT_REGEX, message: SAFE_TEXT_MESSAGE },
            ]}
          >
            <Input.TextArea
              placeholder="Enter description"
              rows={3}
              maxLength={512}
            />
          </Form.Item>
          <DeploymentScopeFields form={editForm} deployments={deployments} />
        </Form>
      </Modal>
    </SettingsLayout>
  );
}

export { GlobalApiDeploymentKeys };
