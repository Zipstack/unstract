import { useMemo, useEffect, useRef } from "react";
import PropTypes from "prop-types";
import { Table } from "antd";
import { uniqueId } from "lodash";
import { useSocketLogsStore } from "../../store/socket-logs-store";
import "./DisplayLogsAndNotifications.css";
import CustomMarkdown from "../helpers/custom-markdown/CustomMarkdown";
import { getDateTimeString } from "../../helpers/GetStaticData";

function LogsAndNotificationsTable({ errorCount, setErrorCount, isMinimized }) {
  const tableRef = useRef(null);
  const { logs } = useSocketLogsStore();

  useEffect(() => {
    if (!isMinimized && errorCount !== 0) {
      setErrorCount(0);
    }
  }, [isMinimized]);

  const dataSource = useMemo(() => {
    const logMessages = logs.map((log) => {
      if (log?.level === "ERROR" && log?.type === "LOG" && isMinimized) {
        setErrorCount((prev) => prev + 1);
      }
      return {
        key: `${log.timestamp}-${uniqueId()}`,
        time: getDateTimeString(log?.timestamp),
        level: log?.level,
        type: log?.type,
        stage: log?.stage,
        step: log?.step,
        state: log?.state,
        promptKey: log?.component?.prompt_key,
        docName: log?.component?.doc_name,
        message: (
          <CustomMarkdown
            text={log?.message}
            styleClassName="display-logs-md"
          />
        ),
      };
    });
    return logMessages;
  }, [logs]);

  const columns = useMemo(
    () => [
      {
        title: "Time",
        dataIndex: "time",
        key: "time",
      },
      {
        title: "Level",
        dataIndex: "level",
        key: "level",
      },
      {
        title: "Type",
        dataIndex: "type",
        key: "type",
        filters: [
          { text: "LOG", value: "LOG" },
          { text: "NOTIFICATION", value: "NOTIFICATION" },
        ],
        defaultFilteredValue: [],
        filterMultiple: true,
        onFilter: (value, record) => record.type === value,
      },
      {
        title: "Stage",
        dataIndex: "stage",
        key: "stage",
      },
      {
        title: "Step",
        dataIndex: "step",
        key: "step",
      },
      {
        title: "State",
        dataIndex: "state",
        key: "state",
      },
      {
        title: "Prompt Key",
        dataIndex: "promptKey",
        key: "promptKey",
      },
      {
        title: "Doc Name",
        dataIndex: "docName",
        key: "docName",
      },
      {
        title: "Message",
        dataIndex: "message",
        key: "message",
      },
    ],
    []
  );

  useEffect(() => {
    if (logs?.length && tableRef.current) {
      const body = tableRef.current.querySelector(".ant-table-body");
      if (body) {
        body.scrollTo({
          top: body.scrollHeight,
          behavior: "smooth",
        });
      }
    }
  }, [logs]);

  const rowClassName = (record) => {
    return record.level === "ERROR" ? "display-logs-error-bg" : "";
  };

  return (
    <div className="tool-logs-table" ref={tableRef}>
      <Table
        dataSource={dataSource}
        columns={columns}
        rowClassName={rowClassName}
        pagination={false}
        showHeader
        size="small"
      />
    </div>
  );
}

LogsAndNotificationsTable.propTypes = {
  errorCount: PropTypes.number.isRequired,
  setErrorCount: PropTypes.func.isRequired,
  isMinimized: PropTypes.bool.isRequired,
};

export { LogsAndNotificationsTable };
