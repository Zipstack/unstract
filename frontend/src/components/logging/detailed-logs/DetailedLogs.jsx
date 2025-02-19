import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CalendarOutlined,
  ClockCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { Button, Card, Flex, Table, Typography } from "antd";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./DetailedLogs.css";
import {
  formatSecondsToHMS,
  formattedDateTime,
} from "../../../helpers/GetStaticData";
import { LogModal } from "../log-modal/LogModal";

const DetailedLogs = () => {
  const { id } = useParams(); // Get the ID from the URL
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const [executionDetails, setExecutionDetails] = useState();
  const [executionFiles, setExecutionFiles] = useState();
  const [loading, setLoading] = useState();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [logDescModalOpen, setLogDescModalOpen] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);

  const fetchExecutionDetails = async (id) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${id}`;
      const response = await axiosPrivate.get(url);
      const item = response?.data?.results[0];
      const total = item?.total_files || 0;
      const processed =
        (item?.successful_files || 0) + (item?.failed_files || 0);
      const progress = total > 0 ? Math.round((processed / total) * 100) : 0;
      const formattedData = {
        executedAt: formattedDateTime(item?.created_at),
        executionId: item?.id,
        progress,
        processed,
        total,
        status: item?.status,
        executionName: item?.workflow_name,
        ranFor: formatSecondsToHMS(item?.execution_time),
      };

      setExecutionDetails(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const fetchExecutionFiles = async (id, page) => {
    try {
      const url = `/api/v1/unstract/${sessionDetails?.orgId}/execution/${id}/files/`;
      const response = await axiosPrivate.get(url, {
        params: {
          page_size: pagination.pageSize,
          page,
        },
      });
      // Replace with your actual API URL
      setPagination({
        current: page,
        pageSize: pagination?.pageSize,
        total: response?.data?.count, // Total number of records
      });
      const formattedData = response?.data?.results.map((item, index) => {
        return {
          key: `${index.toString()}-${item?.id}`,
          fileName: item?.file_name,
          statusMessage: item?.latest_log || "Yet to be processed",
          fileSize: item?.file_size,
          status: item?.status,
          executedAt: formattedDateTime(item?.created_at),
          executionTime: item?.execution_time,
          executionId: item?.id,
        };
      });

      setExecutionFiles(formattedData);
    } catch (err) {
      setAlertDetails(handleException(err));
    } finally {
      setLoading(false);
    }
  };

  const columnsDetailedTable = [
    {
      title: "File Name",
      dataIndex: "fileName",
      key: "fileName",
    },
    {
      title: "Status Message",
      dataIndex: "statusMessage",
      key: "statusMessage",
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
    },
    {
      title: "File Size",
      dataIndex: "fileSize",
      key: "fileSize",
    },
    {
      title: "Execution Time",
      dataIndex: "executionTime",
      key: "executionTime",
    },
    {
      title: "Executed At",
      dataIndex: "executedAt",
      key: "executedAt",
    },
    {
      title: "Action",
      dataIndex: "action",
      key: "action",
      render: (_, record) => (
        <Button
          icon={<EyeOutlined />}
          onClick={() => handleLogsModalOpen(record)}
        ></Button>
      ),
    },
  ];

  const handleLogsModalOpen = (record) => {
    setLogDescModalOpen(true);
    setSelectedRecord(record);
  };

  useEffect(() => {
    fetchExecutionDetails(id);
    fetchExecutionFiles(id, pagination.current);
  }, [pagination.current]);

  return (
    <>
      <Typography.Title className="logs-title" level={4}>
        ETL Session ID - {id}{" "}
      </Typography.Title>
      <Flex className="pad-12">
        <Card className="logs-details-card">
          <Flex justify="flex-start" align="center">
            <CalendarOutlined className="logging-card-icons" />
            <div>
              <Typography className="logging-card-title">Started</Typography>
              <Typography>{executionDetails?.executedAt}</Typography>
            </div>
          </Flex>
        </Card>
        <Card className="logs-details-card">
          <Flex justify="flex-start" align="center">
            <ClockCircleOutlined className="logging-card-icons" />
            <div>
              <Typography className="logging-card-title">Ran for</Typography>
              <Typography>{executionDetails?.ranFor}</Typography>
            </div>
          </Flex>
        </Card>
        <Card className="logs-details-card">
          <Flex justify="flex-start" align="center">
            <FileTextOutlined className="logging-card-icons" />
            <div>
              <Typography className="logging-card-title">
                Processed files
              </Typography>
              <Typography>
                {executionDetails?.processed}/{executionDetails?.total}{" "}
                {executionDetails?.processed > 0 && "Successfully"}
              </Typography>
            </div>
          </Flex>
        </Card>
      </Flex>
      <div className="settings-layout">
        <Table
          dataSource={executionFiles}
          columns={columnsDetailedTable}
          pagination={pagination}
          loading={loading}
        />
      </div>
      <LogModal
        executionId={id}
        fileId={selectedRecord?.executionId}
        logDescModalOpen={logDescModalOpen}
        setLogDescModalOpen={setLogDescModalOpen}
      />
    </>
  );
};

export { DetailedLogs };
