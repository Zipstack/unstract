import {
  ArrowRightOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { Space, Typography } from "antd";
import { useEffect, useState } from "react";

import { useAlertStore } from "../../../store/alert-store";
import { workflowService } from "../../workflows/workflow/workflow-service.js";
import actionItem from "../action-item/ActionItem.js";
import { AppDeployment } from "../app-deployment/AppDeployment.jsx";
import customActionsColumn from "../custom-columns/CustomActionsColumn.js";
import customLinkColumn from "../custom-columns/CustomLinkColumn.js";
// Uncomment below line when enabling status update
// import customSwitchColumn from "../custom-columns/CustomSwitchColumn.js";
import { Layout } from "../../deployments/layout/Layout.jsx";
import { DeleteModal } from "../delete-modal/DeleteModal.jsx";
import "./AppDeployments.css";
import { appDeploymentsService } from "./app-deployments-service.js";

function AppDeployments() {
  const { setAlertDetails } = useAlertStore();
  const appDeploymentsApiService = appDeploymentsService();

  const [isTableLoading, setIsTableLoading] = useState(false);
  const [openAddAppModal, setOpenAddAppModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [selectedRow, setSelectedRow] = useState({});
  const [tableData, setTableData] = useState([]);
  const [isEdit, setIsEdit] = useState(false);
  const [workflowList, setWorkflowList] = useState([]);
  const workflowApiService = workflowService();

  useEffect(() => {
    getAppDeploymentList();
    getWorkflows();
  }, []);

  const getWorkflows = () => {
    workflowApiService
      .getWorkflowList()
      .then((res) => {
        setWorkflowList(res?.data);
      })
      .catch(() => {
        setAlertDetails({
          type: "error",
          content: "Unable to get workflow list.",
        });
      });
  };

  const getAppDeploymentList = () => {
    setIsTableLoading(true);

    appDeploymentsApiService
      .getAppDeploymentsList()
      .then((res) => {
        setTableData(res?.data);
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: JSON.stringify(err?.response?.data?.detail),
        });
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  };

  const deleteappDeployment = () => {
    appDeploymentsApiService
      .deleteAppDeployment(selectedRow.id)
      .then((res) => {
        setOpenDeleteModal(false);
        getAppDeploymentList();
        setAlertDetails({
          type: "success",
          content: "App Deployment Deleted Successfully",
        });
      })
      .catch((err) => {
        setAlertDetails({
          type: "error",
          content: err?.response?.data?.detail || "Something went wrong",
        });
      });
  };

  // Uncomment when enabling status update
  // const updateStatus = (record) => {
  //   setIsTableLoading(true);
  //   record.is_active = !record?.is_active;
  //   appDeploymentsApiService
  //     .updateAppDeployment(record)
  //     .then((res) => {
  //       setAlertDetails({
  //         type: "success",
  //         content: "Status updated successfully",
  //       });
  //     })
  //     .catch((err) => {
  //       setAlertDetails({
  //         type: "error",
  //         content: JSON.stringify(err?.response?.data?.detail),
  //       });
  //     })
  //     .finally(() => {
  //       setIsTableLoading(false);
  //     });
  // };

  // Uncomment when enabling edit
  // const openEditModal = () => {
  //   setIsEdit(true);
  //   setOpenAddAppModal(true);
  // };

  const openAddModal = () => {
    setIsEdit(false);
    setOpenAddAppModal(true);
  };

  const showDeleteModal = () => {
    setOpenDeleteModal(true);
  };

  const actionItems = [
    {
      key: "1",
      label: actionItem({
        text: "Edit",
        icon: <EditOutlined />,
        // Remove below comment when enabling edit
        // action: openEditModal,
      }),
      disabled: true,
    },
    {
      key: "2",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() =>
            window.open(
              `${window.location.protocol}//${selectedRow?.fqdn}`,
              "_blank"
            )
          }
        >
          <div>
            <ArrowRightOutlined />
          </div>
          <div>
            <Typography.Text>Go to App</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "3",
      label: actionItem({
        text: "Delete",
        icon: <DeleteOutlined />,
        action: showDeleteModal,
      }),
    },
  ];

  const columns = [
    {
      title: "App Name",
      key: "application_name",
      render: (_, record) => (
        <Typography.Text strong>{record?.application_name}</Typography.Text>
      ),
      align: "left",
    },
    {
      title: "Description",
      key: "description",
      render: (_, record) => <Space>{record?.description}</Space>,
      align: "left",
    },
    {
      title: "URL",
      key: "fqdn",
      render: (_, record) => (
        <Space>{`${window.location.protocol}//${record?.fqdn}`}</Space>
      ),
      align: "left",
    },
    customLinkColumn({
      title: "Workflow",
      key: "workflow_name",
      align: "left",
      tooltip: "view workflow",
    }),
    // Uncomment below line when enabling status update
    // customSwitchColumn({ updateStatus }),
    customActionsColumn({ actionItems, setSelectedRow }),
  ];

  return (
    <>
      <Layout
        type="app"
        columns={columns}
        tableData={tableData}
        isTableLoading={isTableLoading}
        openAddModal={openAddModal}
      />
      {openAddAppModal && (
        <AppDeployment
          open={openAddAppModal}
          setOpen={setOpenAddAppModal}
          setTableData={setTableData}
          isEdit={isEdit}
          selectedRow={selectedRow}
          setSelectedRow={setSelectedRow}
          workflowList={workflowList}
        />
      )}
      <DeleteModal
        open={openDeleteModal}
        setOpen={setOpenDeleteModal}
        deleteRecord={deleteappDeployment}
      />
    </>
  );
}

export { AppDeployments };
