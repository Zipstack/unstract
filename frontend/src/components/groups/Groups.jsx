import {
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  PlusOutlined,
  ReloadOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Dropdown, Modal, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { useExceptionHandler } from "../../hooks/useExceptionHandler.jsx";
import { IslandLayout } from "../../layouts/island-layout/IslandLayout.jsx";
import { useAlertStore } from "../../store/alert-store";
import { CustomButton } from "../widgets/custom-button/CustomButton.jsx";
import { SpinnerLoader } from "../widgets/spinner-loader/SpinnerLoader.jsx";
import { TopBar } from "../widgets/top-bar/TopBar.jsx";

import { GroupCreateEditModal } from "./GroupCreateEditModal.jsx";
import { GroupMemberManager } from "./GroupMemberManager.jsx";
import { groupsService } from "./groups-service.js";
import "./Groups.css";

function Groups() {
  const service = groupsService();
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();

  const [groupList, setGroupList] = useState([]);
  const [filteredGroupList, setFilteredGroupList] = useState([]);
  const [isTableLoading, setIsTableLoading] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editorMode, setEditorMode] = useState("create");
  const [membersOpen, setMembersOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmDeleteLoading, setConfirmDeleteLoading] = useState(false);

  const refresh = () => {
    setIsTableLoading(true);
    service
      .listGroups()
      .then((res) => {
        const items = Array.isArray(res?.data) ? res.data : [];
        setGroupList(
          items.map((g) => ({
            key: g.id,
            id: g.id,
            name: g.name,
            description: g.description,
            source: g.source,
            is_managed_externally: g.is_managed_externally,
            member_count: g.member_count ?? 0,
          })),
        );
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load groups"));
      })
      .finally(() => setIsTableLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    setFilteredGroupList(groupList);
  }, [groupList]);

  const handleCreate = () => {
    setSelectedGroup(null);
    setEditorMode("create");
    setEditorOpen(true);
  };

  const handleEdit = (record) => {
    setSelectedGroup(record);
    setEditorMode("edit");
    setEditorOpen(true);
  };

  const handleManageMembers = (record) => {
    setSelectedGroup(record);
    setMembersOpen(true);
  };

  const handleDeleteClick = (record) => {
    setSelectedGroup(record);
    setDeleteOpen(true);
  };

  const confirmDelete = () => {
    if (!selectedGroup) {
      return;
    }
    setConfirmDeleteLoading(true);
    service
      .deleteGroup(selectedGroup.id)
      .then(() => {
        setAlertDetails({ type: "success", content: "Group deleted" });
        setDeleteOpen(false);
        refresh();
      })
      .catch((err) =>
        setAlertDetails(handleException(err, "Failed to delete group")),
      )
      .finally(() => setConfirmDeleteLoading(false));
  };

  const buildActionItems = (record) => {
    const items = [
      {
        key: "members",
        label: (
          <Space onClick={() => handleManageMembers(record)}>
            <TeamOutlined />
            <span>Manage members</span>
          </Space>
        ),
      },
    ];
    if (!record.is_managed_externally) {
      items.push({
        key: "edit",
        label: (
          <Space onClick={() => handleEdit(record)}>
            <EditOutlined />
            <span>Edit</span>
          </Space>
        ),
      });
      items.push({
        key: "delete",
        label: (
          <Space onClick={() => handleDeleteClick(record)}>
            <DeleteOutlined />
            <span>Delete</span>
          </Space>
        ),
      });
    }
    return items;
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      render: (name, record) => (
        <Space size="small">
          <span>{name}</span>
          {record.source === "IDP" && <Tag color="blue">IdP</Tag>}
        </Space>
      ),
    },
    { title: "Description", dataIndex: "description" },
    { title: "Members", dataIndex: "member_count", align: "center" },
    {
      title: "Actions",
      align: "center",
      render: (_, record) => (
        <Dropdown
          menu={{ items: buildActionItems(record) }}
          trigger={["click"]}
          placement="bottomLeft"
        >
          <EllipsisOutlined rotate={90} style={{ cursor: "pointer" }} />
        </Dropdown>
      ),
    },
  ];

  return (
    <>
      <TopBar
        enableSearch={true}
        title="Manage Groups"
        searchData={groupList}
        setFilteredUserList={setFilteredGroupList}
      >
        <CustomButton
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleCreate}
        >
          New Group
        </CustomButton>
        <Button
          shape="circle"
          icon={<ReloadOutlined />}
          onClick={refresh}
          className="groups-reload-button"
        />
      </TopBar>
      <div className="groups-bg-col">
        <IslandLayout>
          <div className="groups-table">
            <Table
              columns={columns}
              dataSource={filteredGroupList}
              size="small"
              loading={{
                indicator: <SpinnerLoader />,
                spinning: isTableLoading,
              }}
            />
          </div>
        </IslandLayout>
      </div>
      <GroupCreateEditModal
        open={editorOpen}
        mode={editorMode}
        group={selectedGroup}
        onClose={() => setEditorOpen(false)}
        onSaved={() => {
          setEditorOpen(false);
          refresh();
        }}
      />
      <GroupMemberManager
        open={membersOpen}
        group={selectedGroup}
        onClose={() => {
          setMembersOpen(false);
          refresh();
        }}
      />
      <Modal
        title="Delete group"
        open={deleteOpen}
        onOk={confirmDelete}
        confirmLoading={confirmDeleteLoading}
        onCancel={() => setDeleteOpen(false)}
        centered
      >
        <Typography>Delete group</Typography>
        <Typography.Text strong>{selectedGroup?.name}</Typography.Text>
        <Typography style={{ marginTop: 12 }}>
          Members will lose access to any resources currently shared with this
          group (unless they have direct or org-wide access).
        </Typography>
      </Modal>
    </>
  );
}

export { Groups };
