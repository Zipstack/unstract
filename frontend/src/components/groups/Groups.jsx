import {
  EllipsisVertical,
  Pencil,
  Plus,
  RotateCw,
  Trash2,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Dropdown, Modal } from "@/components/ui/shims/antd-overlays";
import { Table } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";

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

const getDeleteImpactText = (deleteImpact, memberCount) => {
  if (deleteImpact.loading) {
    return "Checking affected resources…";
  }
  if (deleteImpact.resourceCount === null) {
    return "Members will lose access to any resources currently shared with this group (unless they have direct or org-wide access).";
  }
  const resources = `${deleteImpact.resourceCount} resource${
    deleteImpact.resourceCount === 1 ? "" : "s"
  }`;
  const members = `${memberCount} member${memberCount === 1 ? "" : "s"}`;
  return `Deleting will revoke access to ${resources} for ${members} (unless they have direct or org-wide access).`;
};

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
  const [deleteImpact, setDeleteImpact] = useState({
    loading: false,
    resourceCount: null,
  });

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
    setDeleteImpact({ loading: true, resourceCount: null });
    service
      .listGroupResources(record.id)
      .then((res) => {
        const rows = Array.isArray(res?.data) ? res.data : [];
        setDeleteImpact({ loading: false, resourceCount: rows.length });
      })
      .catch(() => {
        // Non-blocking: fall back to a generic warning if the impact lookup
        // fails. The deletion itself doesn't depend on this fetch.
        setDeleteImpact({ loading: false, resourceCount: null });
      });
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

  const buildActionItems = (record) => [
    {
      key: "members",
      label: (
        <Space onClick={() => handleManageMembers(record)}>
          <Users />
          <span>Manage members</span>
        </Space>
      ),
    },
    {
      key: "edit",
      label: (
        <Space onClick={() => handleEdit(record)}>
          <Pencil />
          <span>Edit</span>
        </Space>
      ),
    },
    {
      key: "delete",
      label: (
        <Space onClick={() => handleDeleteClick(record)}>
          <Trash2 />
          <span>Delete</span>
        </Space>
      ),
    },
  ];

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      render: (name) => <span>{name}</span>,
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
          {/*
           * The trigger has to be a real, named button. A bare icon merged the
           * Dropdown's trigger props onto the <svg>, which puts no node in the
           * accessibility tree: the only way to reach Manage members / Edit /
           * Delete was a mouse. `rotate` came across from antd's icon font and
           * does nothing on a lucide SVG — EllipsisVertical is the glyph it
           * was asking for, and the same one the card kebab menus use.
           */}
          <Button
            type="text"
            icon={<EllipsisVertical />}
            aria-label={`Actions for ${record?.name}`}
          />
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
        searchKey="name"
        searchPlaceholder="Search Groups"
      >
        <CustomButton type="primary" icon={<Plus />} onClick={handleCreate}>
          New Group
        </CustomButton>
        <Button
          shape="circle"
          icon={<RotateCw />}
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
          {getDeleteImpactText(deleteImpact, selectedGroup?.member_count ?? 0)}
        </Typography>
      </Modal>
    </>
  );
}

export { Groups };
