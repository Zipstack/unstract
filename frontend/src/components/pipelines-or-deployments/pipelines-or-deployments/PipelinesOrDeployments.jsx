import {
  ArrowRightOutlined,
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  EyeOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { Dropdown, Image, Space, Switch, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";
import "./PipelinesOrDeployments.css";
import { listOfAppDeployments } from "../../../helpers/GetStaticData";

import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader.jsx";
import { DeleteModal } from "../delete-modal/DeleteModal.jsx";
import { EtlTaskDeploy } from "../etl-task-deploy/EtlTaskDeploy.jsx";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar.jsx";

function PipelinesOrDeployments({ type }) {
  const [headerText, setHeaderText] = useState("");
  const [modalTitle, setModalTitle] = useState("");
  const [tableData, setTableData] = useState([]);
  const [openEtlOrTaskModal, setOpenEtlOrTaskModal] = useState(false);
  const [openDeleteModal, setOpenDeleteModal] = useState(false);
  const [selectedPorD, setSelectedPorD] = useState({});

  // TODO: add appdeployment management logic when it is available
  useEffect(() => {
    setHeaderText("App Deployments");
    setModalTitle("Deploy App");
  }, [type]);

  const actionItems = [
    {
      key: "1",
      label: (
        <Space direction="horizontal" className="action-items">
          <div>
            <EditOutlined />
          </div>
          <div>
            <Typography.Text>Edit</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "2",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          onClick={() => setOpenDeleteModal(true)}
        >
          <div>
            <DeleteOutlined />
          </div>
          <div>
            <Typography.Text>Delete</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "3",
      label: (
        <Space direction="horizontal" className="action-items">
          <div>
            <EyeOutlined />
          </div>
          <div>
            <Typography.Text>View Logs</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "4",
      label: (
        <Space direction="horizontal" className="action-items">
          <div>
            <InfoCircleOutlined />
          </div>
          <div>
            <Typography.Text>View Information</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "5",
      label: (
        <Space direction="horizontal" className="action-items">
          <div>
            <SyncOutlined />
          </div>
          <div>
            <Typography.Text>Sync Now</Typography.Text>
          </div>
        </Space>
      ),
    },
    {
      key: "6",
      label: (
        <Space
          direction="horizontal"
          className="action-items"
          // TODO: Handle the link dynamically
          onClick={() => window.open(selectedPorD?.goto, "_blank")}
        >
          <div>
            <ArrowRightOutlined />
          </div>
          <div>
            <Typography.Text disabled={type !== "app"}>
              Go to App
            </Typography.Text>
          </div>
        </Space>
      ),
      disabled: type !== "app",
    },
  ];

  const columns = [
    {
      title: "Source",
      render: (_, record) => (
        <div>
          <div>
            <Image src={record?.source_icon} preview={false} width={30} />
          </div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.source_name}
          </Typography.Text>
        </div>
      ),
      key: "source",
      align: "center",
    },
    {
      title: "Pipeline",
      key: "pipeline_name",
      render: (_, record) => (
        <>
          <Typography.Text strong>{record?.pipeline_name}</Typography.Text>
          <br />
          <Typography.Text type="secondary" className="p-or-d-typography">
            from {record?.workflow_name}
          </Typography.Text>
        </>
      ),
      align: "center",
    },
    {
      title: "Destination",
      render: (_, record) => (
        <div>
          <div>
            <Image src={record?.destination_icon} preview={false} width={30} />
          </div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.destination_name}
          </Typography.Text>
        </div>
      ),
      key: "destination",
      align: "center",
    },
    {
      title: "Status",
      dataIndex: "last_run_status",
      key: "last_run_status",
      align: "center",
      render: (_, record) => (
        <>
          {record.last_run_status === "processing" ? (
            <SpinnerLoader />
          ) : (
            <Typography.Text className="p-or-d-typography" strong>
              {record?.last_run_status}
            </Typography.Text>
          )}
        </>
      ),
    },
    {
      title: "Last Run",
      key: "last_run_time",
      dataIndex: "last_run_time",
      align: "center",
      render: (_, record) => (
        <div>
          <Typography.Text className="p-or-d-typography" strong>
            {record?.last_run_time}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "Enabled",
      key: "active",
      dataIndex: "active",
      align: "center",
      render: (_, record) => <Switch checked={record.active} />,
    },
    {
      title: "Actions",
      key: "pipeline_id",
      align: "center",
      render: (_, record) => (
        <Dropdown
          menu={{ items: actionItems }}
          placement="bottomLeft"
          onOpenChange={() => setSelectedPorD(record)}
        >
          <EllipsisOutlined rotate={90} className="p-or-d-actions" />
        </Dropdown>
      ),
    },
  ];
  return (
    <div className="p-or-d-layout">
      <ToolNavBar
        title={headerText}
        CustomButtons={() => {
          return (
            <CustomButton
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setOpenEtlOrTaskModal(true)}
              disabled={true}
            >
              App Deployment
            </CustomButton>
          );
        }}
      />
      <div className="p-or-d-body1">
        <div className="p-or-d-body2">
          <div className="p-or-d-table">
            {!tableData || tableData?.length === 0 ? (
              <EmptyState text="Coming soon" />
            ) : (
              <div>
                <Table
                  size="small"
                  columns={columns}
                  dataSource={tableData}
                  rowKey="id"
                />
              </div>
            )}
          </div>
        </div>
      </div>
      <EtlTaskDeploy
        open={openEtlOrTaskModal}
        setOpen={setOpenEtlOrTaskModal}
        setTableData={setTableData}
        type={type}
        title={modalTitle}
      />
      <DeleteModal open={openDeleteModal} setOpen={setOpenDeleteModal} />
    </div>
  );
}

PipelinesOrDeployments.propTypes = {
  type: PropTypes.string.isRequired,
};

export { PipelinesOrDeployments };
