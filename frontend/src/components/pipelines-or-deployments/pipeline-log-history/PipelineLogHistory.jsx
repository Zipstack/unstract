import { useEffect, useState } from "react";
import { Modal, Table, Typography, Tooltip, Button } from "antd";
import PropTypes from "prop-types";
import { FileTextOutlined } from "@ant-design/icons";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import {
  listOfPipelineLogs,
  formattedDateTime,
  titleCase,
} from "../../../helpers/GetStaticData";
import PipelineLogs from "../pipeline-logs/PipelineLogs.jsx";

const PipelineLogHistory = ({ pipeline, open, setOpen }) => {
  const axiosPrivate = useAxiosPrivate();
  const [render, setRender] = useState(false);
  const [logRow, setLogRow] = useState({});
  const [tableRows, setTableRows] = useState([]);
  const [openLogModal, setOpenLogModal] = useState(false);
  const handleCancel = () => {
    setOpen(false);
  };

  useEffect(() => {
    setLogRow({});
    getData();
  }, [render]);

  const closeModal = () => {
    setOpenLogModal(false);
    setRender((prev) => !prev);
  };

  const getData = () => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/mock_org/api/deployment/`,
      //   url: `/api/v1//${pipelineId}`,
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        // setTableRows(res.data?.runHistory);
        setTableRows(listOfPipelineLogs);
      })
      .catch((error) => {})
      .finally(() => {});
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
      render: (_, record) => (
        <div>
          <Tooltip title="View Logs" placement="bottom">
            <Button size="small" onClick={(e) => handleOpenLogModal(record)}>
              <FileTextOutlined />
            </Button>
          </Tooltip>
        </div>
      ),
    },
  ];

  const handleOpenLogModal = (rowData) => {
    setLogRow(rowData);
    setOpenLogModal(true);
  };

  // eslint-disable-next-line react/prop-types
  const CustomTitle = ({ title, subtitle }) => (
    <div>
      <div style={{ fontSize: 24, fontWeight: "bold" }}>{title}</div>
      <div style={{ fontSize: 16 }}>{subtitle}</div>
    </div>
  );

  return (
    <>
      <Modal
        title={
          <CustomTitle
            title="ETL Runs"
            subtitle={`Logs for ${pipeline?.pipeline_type} Pipeline : ${pipeline?.pipeline_name}`}
          />
        }
        centered
        maskClosable={false}
        open={open}
        footer={null}
        onCancel={handleCancel}
        width={1000}
      >
        <Table
          columns={columns}
          dataSource={tableRows}
          size="small"
          bordered
          max-width="100%"
          pagination={{ pageSize: 10 }}
        />
      </Modal>
      <PipelineLogs
        open={openLogModal}
        closeModal={closeModal}
        logRow={logRow}
      />
    </>
  );
};

PipelineLogHistory.propTypes = {
  pipeline: PropTypes.object.isRequired,
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};

export { PipelineLogHistory };
