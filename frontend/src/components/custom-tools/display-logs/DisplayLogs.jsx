import { useEffect, useRef } from "react";
import { Col, Row, Typography } from "antd";

import "../../agency/display-logs/DisplayLogs.css";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import { uniqueId } from "lodash";
import {
  convertTimestampToHHMMSS,
  isSubPage,
} from "../../../helpers/GetStaticData";
import { useLocation } from "react-router-dom";

function DisplayLogs() {
  const bottomRef = useRef(null);
  const { logs } = useSocketLogsStore();
  const location = useLocation(); // Get the current route location
  const isWorkflowSubPage = isSubPage("workflows", location.pathname);
  const isPromptStudioPage = isSubPage("tools", location.pathname);

  useEffect(() => {
    if (logs?.length) {
      // Scroll down to the lastest chat.
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  return (
    <div className="tool-logs">
      {logs.map((log) => {
        return (
          <div
            key={`${log?.timestamp}-${uniqueId()}`}
            className={`display-logs-container ${
              log?.level === "ERROR" && "display-logs-error-bg"
            }`}
          >
            <Row>
              <Col span={2}>
                <Typography className="display-logs-col-first">
                  {convertTimestampToHHMMSS(log?.timestamp)}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.level}
                </Typography>
              </Col>
              <Col span={3}>
                <Typography className="display-logs-col">
                  {log?.type}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.stage}
                </Typography>
              </Col>
              {isWorkflowSubPage && (
                <>
                  <Col span={2}>
                    <Typography className="display-logs-col">
                      {log?.step}
                    </Typography>
                  </Col>
                  <Col span={2}>
                    <Typography className="display-logs-col">
                      {log?.state}
                    </Typography>
                  </Col>
                </>
              )}
              {isPromptStudioPage && (
                <>
                  <Col span={2}>
                    <Typography className="display-logs-col">
                      {log?.component?.prompt_key}
                    </Typography>
                  </Col>
                  <Col span={2}>
                    <Typography className="display-logs-col">
                      {log?.component?.doc_name}
                    </Typography>
                  </Col>
                </>
              )}
              <Col span={4}>
                <Typography className="display-logs-col">
                  {log?.message}
                </Typography>
              </Col>
            </Row>
            <div ref={bottomRef} />
          </div>
        );
      })}
    </div>
  );
}

export { DisplayLogs };
