import { useEffect, useRef } from "react";
import { Col, Row, Typography } from "antd";

import "./DisplayLogs.css";
import { useSocketLogsStore } from "../../../store/socket-logs-store";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";

function DisplayLogs() {
  const bottomRef = useRef(null);
  const { logs } = useSocketLogsStore();

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
          <div key={log?.key}>
            <Row>
              <Col span={2}>
                <Typography className="display-logs-col-first">
                  {log?.timestamp}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.stage}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.step}
                </Typography>
              </Col>
              <Col span={8}>
                <CustomMarkdown
                  text={log?.message}
                  renderNewLines={false}
                  styleClassName="display-logs-col"
                />
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.cost_type}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.cost_units}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.cost}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.iteration}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.iteration_total}
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
