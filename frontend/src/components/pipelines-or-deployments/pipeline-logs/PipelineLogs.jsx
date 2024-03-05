import { Modal, Table, Typography } from "antd";
import PropTypes from "prop-types";

import {
  listOfPipelineLogs,
  formattedDateTime,
  titleCase,
} from "../../../helpers/GetStaticData";

const PipelineLogs = ({ open, setOpen }) => {
  const handleCancel = () => {
    setOpen(false);
  };

  const columns = [
    {
      title: "Start Date Time",
      dataIndex: "start_date_time",
      key: "start_date_time",
      render: (_, record) => (
        <div>
          <Typography.Text>
            {formattedDateTime(record?.start_date_time)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "End Date Time",
      dataIndex: "end_date_time",
      key: "end_date_time",
      render: (_, record) => (
        <div>
          <Typography.Text>
            {formattedDateTime(record?.end_date_time)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (_, record) => (
        <div>
          <Typography.Text>{titleCase(record?.status)}</Typography.Text>
        </div>
      ),
    },
    {
      title: "Logs",
      dataIndex: "logid",
      key: "logid",
    },
  ];

  return (
    <Modal
      title={"ETL Runs"}
      centered
      maskClosable={false}
      open={open}
      footer={null}
      onCancel={handleCancel}
      width={900}
    >
      <Table
        columns={columns}
        dataSource={listOfPipelineLogs}
        size="small"
        bordered
        max-width="100%"
        pagination={{ pageSize: 10 }}
      />
    </Modal>
  );
};

PipelineLogs.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};

export { PipelineLogs };
