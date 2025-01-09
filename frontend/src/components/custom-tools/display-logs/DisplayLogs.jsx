import { useEffect, useRef } from "react";
import { Col, Row, Typography } from "antd";

import "../../agency/display-logs/DisplayLogs.css";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { getDateTimeString } from "../../../helpers/GetStaticData";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";

function DisplayLogs() {
  const bottomRef = useRef(null);
  const { messages } = useSocketCustomToolStore();

  useEffect(() => {
    if (messages?.length) {
      // Scroll down to the lastest chat.
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div className="tool-logs">
      {messages.map((message) => {
        return (
          <div key={message?.timestamp}>
            <Row>
              <Col span={5}>
                <Typography className="display-logs-col-first">
                  {getDateTimeString(message?.timestamp)}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {message?.level}
                </Typography>
              </Col>
              <Col span={2}>
                <Typography className="display-logs-col">
                  {message?.state}
                </Typography>
              </Col>
              <Col span={3}>
                <Typography className="display-logs-col">
                  {message?.component?.prompt_key}
                </Typography>
              </Col>
              <Col span={3}>
                <Typography className="display-logs-col">
                  {message?.component?.doc_name}
                </Typography>
              </Col>
              <Col span={8}>
                <CustomMarkdown
                  text={message?.message}
                  styleClassName="display-logs-col"
                />
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
