import { CopyOutlined, DownloadOutlined } from "@ant-design/icons";
import { Button, Dropdown, Modal, Table, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import "./LogModal.css";
import {
  formattedDateTime,
  formattedDateTimeWithSeconds,
} from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useCopyToClipboard } from "../../../hooks/useCopyToClipboard";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import useRequestUrl from "../../../hooks/useRequestUrl";
import { useAlertStore } from "../../../store/alert-store";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";
import { FilterDropdown, FilterIcon } from "../filter-dropdown/FilterDropdown";

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
  const copyToClipboard = useCopyToClipboard();
  const displayId = fileId || executionId;

  const [executionLogs, setExecutionLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
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

  const handleExport = async (fileFormat) => {
    if (exporting) {
      return;
    }
    setExporting(true);
    try {
      const url = getUrl(`/execution/${executionId}/logs/export/`);
      // `file_format` (not `format`) — `format` is reserved by DRF for
      // content negotiation and 404s when set to "csv".
      const params = {
        file_format: fileFormat,
        file_execution_id: fileId || "null",
      };
      // Skip log_level when nothing is selected; axios serializes `null` as
      // the literal string "null" which falls through the level filter to
      // an INFO-min default and silently drops DEBUG rows.
      if (selectedLogLevel) {
        params.log_level = selectedLogLevel;
      }
      const response = await axiosPrivate.get(url, {
        params,
        responseType: "blob",
      });

      const filename =
        response.headers?.["content-disposition"]?.match(
          /filename="?([^"]+)"?/,
        )?.[1] || `execution_logs_${fileId || executionId}.${fileFormat}`;
      const blobUrl = globalThis.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      globalThis.URL.revokeObjectURL(blobUrl);
    } catch (err) {
      // 413 means we hit the server-side row cap. Always surface a
      // narrow-your-filter message — even if decoding the JSON blob body
      // fails we keep the right user-facing copy rather than falling
      // through to a generic "Request failed" alert.
      if (err?.response?.status === 413) {
        let message = "Export too large — narrow your filter and retry.";
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          if (parsed?.error) {
            message = parsed.error;
          }
        } catch (parseErr) {
          console.error("Failed to parse 413 body:", parseErr);
        }
        setAlertDetails({ type: "error", content: message });
        return;
      }
      setAlertDetails(handleException(err));
    } finally {
      setExporting(false);
    }
  };

  const exportMenuItems = [
    {
      key: "json",
      label: "Download as JSON",
      onClick: () => handleExport("json"),
    },
    {
      key: "csv",
      label: "Download as CSV",
      onClick: () => handleExport("csv"),
    },
  ];

  let exportTooltip;
  if (!pagination.total) {
    exportTooltip = "No logs to export";
  } else if (exporting) {
    exportTooltip = "Export in progress…";
  } else {
    exportTooltip = "Export logs";
  }

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
      render: (log) => <CustomMarkdown text={log || ""} />,
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
      title={
        <span className="log-modal-title">
          File Execution ID {displayId}
          {displayId && (
            <Button
              className="copy-btn-outlined"
              icon={<CopyOutlined />}
              aria-label="Copy execution ID"
              onClick={() => copyToClipboard(displayId, "File Execution ID")}
            />
          )}
          <Dropdown
            menu={{ items: exportMenuItems }}
            trigger={["click"]}
            disabled={!pagination.total || exporting}
          >
            <Tooltip title={exportTooltip}>
              {/* span wrapper — antd disabled Buttons swallow pointer
                  events so a direct Tooltip child never receives
                  mouseenter and the disabled-state tooltip never shows. */}
              <span>
                <Button
                  className="export-btn-outlined"
                  icon={<DownloadOutlined />}
                  loading={exporting}
                  disabled={!pagination.total || exporting}
                >
                  Export
                </Button>
              </span>
            </Tooltip>
          </Dropdown>
        </span>
      }
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
