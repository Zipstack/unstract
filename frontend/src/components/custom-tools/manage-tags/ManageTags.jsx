import { Modal, Space, Table, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import "./ManageTags.css";

function ManageTags({ open, setOpen }) {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    setRows([]);
  }, []);

  const columns = [
    {
      title: "Tag",
      dataIndex: "tag",
      key: "tag",
      width: 500,
    },
    {
      title: "Last Saved",
      dataIndex: "updated",
      key: "updated",
    },
    {
      title: "",
      dataIndex: "load",
      key: "load",
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
              Manage Tags
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

ManageTags.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};
export { ManageTags };
