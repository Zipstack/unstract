import { useState } from "react";
import { Modal, Table, Tag, Space } from "antd";
import PropTypes from "prop-types";

const TagManagerModal = ({ open, onClose }) => {
  const [data] = useState([
    {
      key: "1",
      tag: { name: "Important", color: "red" },
      lastSaved: "2024-03-25T08:00:00Z", // Example timestamp
    },
    {
      key: "2",
      tag: { name: "Work", color: "blue" },
      lastSaved: "2024-07-13T16:15:00Z", // Example timestamp
    },
    // Add more rows as needed
  ]);

  const columns = [
    {
      title: "Tag",
      dataIndex: "tag",
      key: "tag",
      render: (tag) => <Tag color={tag.color}>{tag.name}</Tag>,
    },
    {
      title: "Last Saved",
      dataIndex: "lastSaved",
      key: "lastSaved",
      render: (lastSaved) => {
        const date = new Date(lastSaved);
        const options = { month: "long", day: "numeric", year: "numeric" };
        const formattedDate = date.toLocaleDateString("en-US", options);

        // Add suffix for day (e.g., 1st, 2nd, 3rd, 4th)
        const day = date.getDate();
        const suffix =
          day === 1 ? "st" : day === 2 ? "nd" : day === 3 ? "rd" : "th";
        return `${formattedDate}${suffix}, ${date.getFullYear()}`;
      },
    },
    {
      title: "Actions",
      key: "actions",
      render: () => (
        <Space size="middle">
          <a>Load</a>
          <a>Delete</a>
        </Space>
      ),
    },
  ];

  return (
    <Modal open={open} title="Tag Data" onCancel={onClose} footer={null}>
      <Table columns={columns} dataSource={data} />
    </Modal>
  );
};
TagManagerModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};
export { TagManagerModal };
