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
  Form,
  Input,
  Modal,
  Switch,
  Table,
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
import "./ApiKeyManager.css";

// Allow-list for user-facing free text (key name/description). Matches the
// backend's utils.input_sanitizer.SAFE_TEXT_PATTERN — alphanumerics, spaces and
// a small set of punctuation (incl. apostrophe); no angle brackets/quotes/&
// that could break out of an HTML attribute when rendered in emails/PDFs/logs.
const SAFE_TEXT_REGEX = /^[a-zA-Z0-9 \-_.,:'()/]+$/;
const SAFE_TEXT_MESSAGE =
  "Only alphanumeric characters, spaces, hyphens, underscores, periods, commas, colons, apostrophes, parentheses, and forward slashes are allowed.";

const identity = (v) => v;

/**
 * Shared key-management screen for platform API keys and global API deployment
 * keys. Owns the common table + create/edit/rotate/delete/copy flows; callers
 * inject the feature-specific bits (extra column, extra form fields, payload
 * shaping, edit initial values) via props.
 */
function ApiKeyManager({
  title,
  entityLabel,
  resourcePath,
  extraColumns = [],
  renderCreateFields,
  renderEditFields,
  getEditInitialValues = () => ({}),
  transformCreatePayload = identity,
  transformEditPayload = identity,
}) {
  const [keys, setKeys] = useState([]);
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

  const basePath = `/api/v1/unstract/${sessionDetails?.orgId}/${resourcePath}`;

  const fetchKeys = useCallback(() => {
    if (!sessionDetails?.orgId) {
      return;
    }
    setIsLoading(true);
    axiosPrivate({ method: "GET", url: `${basePath}/keys/` })
      .then((res) => setKeys(res?.data || []))
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to load API keys")),
      )
      .finally(() => setIsLoading(false));
  }, [basePath, sessionDetails?.orgId]);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = () => {
    createForm
      .validateFields()
      .then((values) => {
        setIsSaving(true);
        axiosPrivate({
          method: "POST",
          url: `${basePath}/keys/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: transformCreatePayload(values),
        })
          .then((res) => {
            setIsCreateModalOpen(false);
            createForm.resetFields();
            fetchKeys();
            copyToClipboard(res?.data?.key, "API key");
          })
          .catch((err) =>
            setAlertDetails(handleException(err, "Failed to create API key")),
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
        axiosPrivate({
          method: "PATCH",
          url: `${basePath}/keys/${selectedKey?.id}/`,
          headers: {
            "X-CSRFToken": sessionDetails?.csrfToken,
            "Content-Type": "application/json",
          },
          data: transformEditPayload(values),
        })
          .then(() => {
            setIsEditModalOpen(false);
            editForm.resetFields();
            setSelectedKey(null);
            fetchKeys();
            setAlertDetails({
              type: "success",
              content: "API key updated successfully",
            });
          })
          .catch((err) =>
            setAlertDetails(handleException(err, "Failed to update API key")),
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
        setAlertDetails(handleException(err, "Failed to rotate API key")),
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
          content: "API key deleted successfully",
        });
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to delete API key")),
      );
  };

  const openEditModal = (record) => {
    setSelectedKey(record);
    editForm.setFieldsValue({
      description: record?.description,
      ...getEditInitialValues(record),
    });
    setIsEditModalOpen(true);
  };

  const handleCopyKey = (record) => {
    axiosPrivate({ method: "GET", url: `${basePath}/keys/${record?.id}/` })
      .then((res) => copyToClipboard(res?.data?.key, "API key"))
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to copy API key")),
      );
  };

  const formatDate = (dateStr) =>
    dateStr ? new Date(dateStr).toLocaleString() : "";

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      width: "13%",
      ellipsis: true,
    },
    {
      title: "Description",
      dataIndex: "description",
      key: "description",
      width: "15%",
      ellipsis: true,
    },
    {
      title: "API Key",
      dataIndex: "key",
      key: "key",
      width: "14%",
      render: (_, record) => (
        <Tooltip title="Click to copy">
          <Button
            type="text"
            className="api-key-manager__key-cell"
            onClick={() => handleCopyKey(record)}
            aria-label={`Copy API key ${record?.name}`}
          >
            <Typography.Text className="api-key-manager__key-text">
              {record?.key}
            </Typography.Text>
            <CopyOutlined className="api-key-manager__copy-icon" />
          </Button>
        </Tooltip>
      ),
    },
    ...extraColumns,
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
      width: "15%",
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
      width: "12%",
      render: (_, record) => (
        <div className="api-key-manager__actions">
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

  const nameAndDescriptionRules = {
    name: [
      { required: true, message: "Name is required" },
      { max: 128, message: "Name cannot exceed 128 characters" },
      { pattern: SAFE_TEXT_REGEX, message: SAFE_TEXT_MESSAGE },
    ],
    description: [
      { required: true, message: "Description is required" },
      { max: 512, message: "Description cannot exceed 512 characters" },
      { pattern: SAFE_TEXT_REGEX, message: SAFE_TEXT_MESSAGE },
    ],
  };

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
            {title}
          </Typography.Text>
        </div>
        <div className="plt-set-layout">
          <IslandLayout>
            <div className="api-key-manager__content">
              <div className="api-key-manager__header-actions">
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
        title={`Create ${entityLabel}`}
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
            rules={nameAndDescriptionRules.name}
          >
            <Input placeholder="Enter key name" maxLength={128} />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description"
            rules={nameAndDescriptionRules.description}
          >
            <Input.TextArea
              placeholder="Enter description"
              rows={3}
              maxLength={512}
            />
          </Form.Item>
          {renderCreateFields?.(createForm)}
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title={`Edit ${entityLabel}`}
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
            rules={nameAndDescriptionRules.description}
          >
            <Input.TextArea
              placeholder="Enter description"
              rows={3}
              maxLength={512}
            />
          </Form.Item>
          {renderEditFields?.(editForm)}
        </Form>
      </Modal>
    </SettingsLayout>
  );
}

ApiKeyManager.propTypes = {
  title: PropTypes.string.isRequired,
  entityLabel: PropTypes.string.isRequired,
  resourcePath: PropTypes.string.isRequired,
  extraColumns: PropTypes.array,
  renderCreateFields: PropTypes.func,
  renderEditFields: PropTypes.func,
  getEditInitialValues: PropTypes.func,
  transformCreatePayload: PropTypes.func,
  transformEditPayload: PropTypes.func,
};

export { ApiKeyManager };
