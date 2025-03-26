import { Modal, Table, Tooltip } from "antd";
import { useEffect, useState } from "react";
import PropTypes from "prop-types";

import "./LogModal.css";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { FilterDropdown, FilterIcon } from "../filter-dropdown/FilterDropdown";
import useRequestUrl from "../../../hooks/useRequestUrl";

function LogModal({
  executionId,
  fileId,
  logDescModalOpen,
  setLogDescModalOpen,
  filterParams,
}) {
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const { getUrl } = useRequestUrl();

  const [executionLogs, setExecutionLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedLogLevel, setSelectedLogLevel] = useState(null);
  const [ordering, setOrdering] = useState(null);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const filterOptions = ["INFO", "WARN", "DEBUG", "ERROR"];

  const fetchExecutionFileLogs = async (executionId, fileId, page) => {
    try {
      const url = getUrl(`/execution/${executionId}/logs/`);
      const response = await axiosPrivate.get(url, {
        params: {
          page_size: pagination.pageSize,
          page,
          file_execution_id: fileId || "null",
          log_level: selectedLogLevel,
          ordering,
        },
      });
      // Replace with your actual API URL
      setPagination({
        current: page,
        pageSize: pagination?.pageSize,
        total: response?.data?.count, // Total number of records
      });
      const formattedData = response?.data?.results.map((item) => {
        return {
          key: item?.id,
          eventTime: formattedDateTime(item?.event_time),
          eventStage: item.data?.stage,
          logLevel: item.data?.level,
          log: item?.data?.log,
          executedAtWithSeconds: formattedDateTimeWithSeconds(item?.created_at),
        };
      });

      setExecutionLogs(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setLogDescModalOpen(false);
    setExecutionLogs([]); // Clear logs
    setPagination({ current: 1, pageSize: 10, total: 0 }); // Reset pagination
  };

  const logDetailsColumns = [
    {
      title: "Event Time",
      dataIndex: "eventTime",
      key: "eventTime",
      sorter: true,
      width: 200,
      render: (_, record) => (
        <Tooltip title={record.executedAtWithSeconds}>
          {record.eventTime}
        </Tooltip>
      ),
    },
    {
      title: "Event Stage",
      dataIndex: "eventStage",
      key: "stage",
    },
    {
      title: "Log Level",
      dataIndex: "logLevel",
      key: "level",
      filterDropdown: (props) => (
        <FilterDropdown
          {...props}
          handleClearFilter={handleClearFilter}
          filterOptions={filterOptions}
        />
      ),
      filteredValue: selectedLogLevel ? [selectedLogLevel] : [],
      filterIcon: (filtered) => <FilterIcon filtered={filtered} />,
      render: (level) => <span className={level?.toLowerCase()}>{level}</span>,
    },
    {
      title: "Log",
      dataIndex: "log",
      key: "log",
    },
  ];

  const handleClearFilter = (confirm) => {
    setSelectedLogLevel(null);
    confirm();
  };

  const handleTableChange = (pagination, filters, sorter) => {
    setPagination((prev) => {
      return { ...prev, ...pagination };
    });

    if (sorter.order) {
      // Determine ascending or descending order
      const executionTimeParam = filterParams.executionTime || "created_at";
      const order =
        sorter.order === "ascend"
          ? executionTimeParam
          : `-${executionTimeParam}`;
      setOrdering(order);
    } else {
      setOrdering(null);
    }
    setSelectedLogLevel(filters.level[0]);
  };

  useEffect(() => {
    if (logDescModalOpen) {
      fetchExecutionFileLogs(executionId, fileId, pagination.current);
    }
  }, [logDescModalOpen, pagination.current, selectedLogLevel, ordering]);
  return (
    <Modal
      title={`Execution Log Details - ${fileId || executionId}`}
      centered
      open={logDescModalOpen}
      onCancel={handleClose}
      footer={null}
      width="80%"
      wrapClassName="modal-body"
      destroyOnClose
    >
      <Table
        columns={logDetailsColumns}
        dataSource={executionLogs}
        rowKey="id"
        align="left"
        pagination={{
          ...pagination,
        }}
        loading={loading}
        onChange={handleTableChange}
        sortDirections={["ascend", "descend", "ascend"]}
      />
    </Modal>
  );
}
LogModal.propTypes = {
  executionId: PropTypes.string,
  fileId: PropTypes.string,
  logDescModalOpen: PropTypes.array,
  setLogDescModalOpen: PropTypes.array,
  filterParams: PropTypes.object,
};

export { LogModal };
