import { DeleteOutlined, QuestionCircleOutlined } from "@ant-design/icons";
import { Avatar, List, Modal, Popconfirm, Select, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useExceptionHandler } from "../../hooks/useExceptionHandler.jsx";
import { useAlertStore } from "../../store/alert-store";
import { SpinnerLoader } from "../widgets/spinner-loader/SpinnerLoader.jsx";

import { groupsService } from "./groups-service.js";

function GroupMemberManager({ open, group, onClose }) {
  const service = groupsService();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();

  const [members, setMembers] = useState([]);
  const [orgUsers, setOrgUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pendingAddIds, setPendingAddIds] = useState([]);

  const isExternallyManaged = !!group?.is_managed_externally;

  const loadMembers = () => {
    if (!group?.id) {
      return;
    }
    setLoading(true);
    Promise.all([service.listGroupMembers(group.id), service.getAllOrgUsers()])
      .then(([memberRes, usersRes]) => {
        setMembers(memberRes?.data || []);
        const all = usersRes?.data?.members || [];
        setOrgUsers(
          all.map((m) => ({
            id: m.id,
            email: m.email,
          })),
        );
      })
      .catch((err) => setAlertDetails(handleException(err, "Failed to load")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (open) {
      loadMembers();
      setPendingAddIds([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, group?.id]);

  const memberIds = new Set(members.map((m) => m.user_id));
  const candidateUsers = orgUsers.filter(
    (u) => !memberIds.has(u.id) && !pendingAddIds.includes(u.id),
  );

  const handleAdd = () => {
    if (!pendingAddIds.length) {
      return;
    }
    setLoading(true);
    service
      .addGroupMembers(group.id, pendingAddIds)
      .then(() => {
        setAlertDetails({ type: "success", content: "Members added" });
        setPendingAddIds([]);
        loadMembers();
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to add members")),
      )
      .finally(() => setLoading(false));
  };

  const handleRemove = (userId) => {
    setLoading(true);
    service
      .removeGroupMember(group.id, userId)
      .then(() => {
        setAlertDetails({ type: "success", content: "Member removed" });
        loadMembers();
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to remove member")),
      )
      .finally(() => setLoading(false));
  };

  return (
    <Modal
      title={`Members — ${group?.name || ""}`}
      open={open}
      onCancel={onClose}
      onOk={handleAdd}
      okText="Add selected"
      okButtonProps={{
        disabled: !pendingAddIds.length || isExternallyManaged,
      }}
      cancelText="Close"
      centered
      width={520}
    >
      {loading ? (
        <SpinnerLoader />
      ) : (
        <>
          {isExternallyManaged ? (
            <Typography.Text type="secondary">
              This group is managed externally (IdP sync). Membership cannot be
              edited from the UI.
            </Typography.Text>
          ) : (
            <Select
              mode="multiple"
              style={{ width: "100%", marginBottom: 12 }}
              placeholder="Add members"
              value={pendingAddIds}
              onChange={setPendingAddIds}
              options={candidateUsers.map((u) => ({
                value: u.id,
                label: u.email,
              }))}
              filterOption={(input, option) =>
                (option?.label ?? "")
                  .toString()
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              showSearch
            />
          )}
          <List
            dataSource={members}
            locale={{ emptyText: "No members yet" }}
            renderItem={(item) => (
              <List.Item
                extra={
                  !isExternallyManaged && (
                    <Popconfirm
                      title="Remove member"
                      description={`Remove ${item.email} from this group?`}
                      okText="Remove"
                      cancelText="Cancel"
                      icon={<QuestionCircleOutlined />}
                      onConfirm={() => handleRemove(item.user_id)}
                    >
                      <DeleteOutlined style={{ cursor: "pointer" }} />
                    </Popconfirm>
                  )
                }
              >
                <List.Item.Meta
                  avatar={
                    <Avatar>{(item.email || "?")[0].toUpperCase()}</Avatar>
                  }
                  title={item.display_name || item.email}
                  description={item.email}
                />
              </List.Item>
            )}
          />
        </>
      )}
    </Modal>
  );
}

GroupMemberManager.propTypes = {
  open: PropTypes.bool.isRequired,
  group: PropTypes.object,
  onClose: PropTypes.func,
};

export { GroupMemberManager };
