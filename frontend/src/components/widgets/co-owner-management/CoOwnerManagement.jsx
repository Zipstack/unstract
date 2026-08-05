import {
  DeleteOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Button,
  List,
  Modal,
  Popconfirm,
  Select,
  Typography,
} from "antd";
import PropTypes from "prop-types";
import { useEffect, useMemo, useState } from "react";

import { SpinnerLoader } from "../spinner-loader/SpinnerLoader";
import "./CoOwnerManagement.css";

function CoOwnerManagement({
  open,
  setOpen,
  resourceId,
  resourceType,
  allUsers,
  coOwners,
  loading,
  onApplyCoOwners,
}) {
  // Staged roster. Adds and removals both edit this list only — nothing reaches
  // the API until Apply, the same contract as the share modal.
  const [selectedOwners, setSelectedOwners] = useState([]);
  const [applying, setApplying] = useState(false);

  const ownersList = useMemo(() => coOwners || [], [coOwners]);

  // Re-seed whenever the server roster changes: on open, on resource switch, and
  // after an Apply. Doubles as the reset — most hosts leave this modal mounted,
  // and the hook can close it without ``handleCancel`` (404 / fetch-error), so
  // staged edits must not leak into the next resource.
  useEffect(() => {
    setSelectedOwners(ownersList);
  }, [ownersList]);

  const selectedIds = useMemo(
    () => new Set(selectedOwners.map((u) => u?.id?.toString())),
    [selectedOwners],
  );

  const availableUsers = useMemo(
    () => (allUsers || []).filter((u) => !selectedIds.has(u?.id?.toString())),
    [allUsers, selectedIds],
  );

  const { addUsers, removeUsers } = useMemo(() => {
    const ownerIds = new Set(ownersList.map((u) => u?.id?.toString()));
    return {
      addUsers: selectedOwners.filter((u) => !ownerIds.has(u?.id?.toString())),
      removeUsers: ownersList.filter(
        (u) => !selectedIds.has(u?.id?.toString()),
      ),
    };
  }, [ownersList, selectedOwners, selectedIds]);

  const hasChanges = addUsers.length > 0 || removeUsers.length > 0;

  const handleSelect = (userId) => {
    const user = (allUsers || []).find(
      (u) => u?.id?.toString() === userId?.toString(),
    );
    if (user) {
      setSelectedOwners((prev) => [...prev, user]);
    }
  };

  const handleRemove = (userId) => {
    setSelectedOwners((prev) =>
      prev.filter((u) => u?.id?.toString() !== userId?.toString()),
    );
  };

  const handleApply = async () => {
    if (!hasChanges) {
      return;
    }
    setApplying(true);
    try {
      // Close only on a clean apply; a partial failure keeps the modal open so
      // the user can see what was rejected and retry.
      if (await onApplyCoOwners(resourceId, { addUsers, removeUsers })) {
        setOpen(false);
      }
    } finally {
      setApplying(false);
    }
  };

  const handleCancel = () => {
    setSelectedOwners(ownersList);
    setOpen(false);
  };

  const filterOption = (input, option) =>
    (option?.label ?? "").toLowerCase().includes(input.toLowerCase());

  return (
    <Modal
      title={`Manage Co-Owners - ${resourceType}`}
      open={open}
      onCancel={handleCancel}
      onOk={handleApply}
      okText={"Apply"}
      confirmLoading={applying}
      okButtonProps={{ disabled: !hasChanges }}
      maskClosable={false}
      centered
      closable={true}
      className="co-owner-modal"
    >
      {loading ? (
        <SpinnerLoader />
      ) : (
        <>
          <Select
            filterOption={filterOption}
            showSearch
            size="middle"
            placeholder="Add a co-owner..."
            value={null}
            className="co-owner-search"
            onChange={(selectedValue) => handleSelect(selectedValue)}
            options={availableUsers.map((user) => ({
              label: user.email,
              value: user.id,
            }))}
          />
          <Typography.Title level={5}>Co-Owners</Typography.Title>
          {selectedOwners.length > 0 ? (
            <List
              dataSource={selectedOwners}
              renderItem={(item) => (
                <List.Item
                  extra={
                    // Keep at least one owner — the backend rejects removing
                    // the last one.
                    selectedOwners.length > 1 && (
                      <div
                        onClick={(event) => event.stopPropagation()}
                        role="none"
                      >
                        <Popconfirm
                          key={`${item.id}-remove`}
                          title="Remove Co-Owner"
                          description={`Are you sure you want to remove '${item?.email}' as co-owner?`}
                          okText="Yes"
                          cancelText="No"
                          icon={<QuestionCircleOutlined />}
                          onConfirm={() => handleRemove(item?.id)}
                        >
                          <Button
                            type="text"
                            size="small"
                            icon={
                              <DeleteOutlined className="action-icon-buttons" />
                            }
                            aria-label={`Remove co-owner ${item?.email}`}
                          />
                        </Popconfirm>
                      </div>
                    )
                  }
                >
                  <List.Item.Meta
                    title={
                      <>
                        <Avatar
                          className="shared-user-avatar"
                          icon={<UserOutlined />}
                        />
                        <Typography.Text className="shared-username">
                          {item.email}
                        </Typography.Text>
                      </>
                    }
                  />
                </List.Item>
              )}
            />
          ) : (
            <Typography>No co-owners yet</Typography>
          )}
        </>
      )}
    </Modal>
  );
}

CoOwnerManagement.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  resourceId: PropTypes.string,
  resourceType: PropTypes.string.isRequired,
  allUsers: PropTypes.array,
  coOwners: PropTypes.array,
  loading: PropTypes.bool,
  onApplyCoOwners: PropTypes.func.isRequired,
};

export { CoOwnerManagement };
