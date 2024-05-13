import { useEffect, useRef } from "react";
import { Col, Row, Typography } from "antd";

import "../../agency/display-logs/DisplayLogs.css";
import { getDateTimeString } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useSocketLogsStore } from "../../../store/socket-logs-store";

function DisplayLogs() {
  const bottomRef = useRef(null);
  const { logs } = useSocketLogsStore();
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();

  useEffect(() => {
    if (logs?.length) {
      // Scroll down to the lastest chat.
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  useEffect(() => {
    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/logs/`,
    };

    axiosPrivate(requestOptions)
      .then((res) => {
        console.log(res);
      })
      .catch((err) => {
        console.log(err);
      });
  });

  return (
    <div className="tool-logs">
      {logs.map((log) => {
        return (
          <div key={log?.timestamp}>
            <Row>
              <Col span={2}>
                <Typography className="display-logs-col-first">
                  {getDateTimeString(log?.timestamp)}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.level}
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
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.state}
                </Typography>
              </Col>
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
              <Col span={2}>
                <Typography className="display-logs-col">
                  {log?.cost}
                </Typography>
              </Col>
              <Col span={4}>
                <Typography className="display-logs-col">
                  {log?.message}
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
