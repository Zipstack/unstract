import { Modal, Space, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./ManageExport.css";

function ManageExport({ open, setOpen }) {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    setRows([]);
  }, []);

  const columns = [
    {
      title: "Exported Tool",
      dataIndex: "exported_tool",
      key: "exported_tool",
      width: 400,
    },
    {
      title: "Tag",
      dataIndex: "tag",
      key: "tag",
    },
    {
      title: "Usage",
      dataIndex: "usage",
      key: "usage",
    },
    {
      title: "",
      dataIndex: "change",
      key: "change",
      width: 80,
    },
    {
      title: "",
      dataIndex: "delete",
      key: "delete",
      width: 80,
    },
  ];

  return (
    <Modal
      className="pre-post-amble-modal"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      maskClosable={false}
      width={1000}
    >
      <div className="pre-post-amble-body">
        <SpaceWrapper>
          <Space>
            <Typography.Text className="add-cus-tool-header">
              Export Manager
            </Typography.Text>
          </Space>
          <div>
            <Table
              columns={columns}
              dataSource={rows}
              size="small"
              bordered
              pagination={{ pageSize: 10 }}
            />
          </div>
        </SpaceWrapper>
      </div>
    </Modal>
  );
}

ManageExport.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};
export { ManageExport };
