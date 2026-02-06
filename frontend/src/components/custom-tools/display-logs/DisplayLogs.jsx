import { useEffect, useRef } from "react";
import { Col, Row, Tag, Typography } from "antd";
import { SearchOutlined } from "@ant-design/icons";

import "../../agency/display-logs/DisplayLogs.css";
import "./DisplayLogs.css";
import { useSocketCustomToolStore } from "../../../store/socket-custom-tool";
import { getDateTimeString } from "../../../helpers/GetStaticData";
import CustomMarkdown from "../../helpers/custom-markdown/CustomMarkdown";

/**
 * Get stage-specific styling for log entries.
 * LOOKUP stage uses purple color scheme for visual distinction.
 */
const getStageStyle = (stage) => {
  switch (stage) {
    case "LOOKUP":
      return {
        color: "purple",
        className: "display-logs-stage-lookup",
      };
    case "RUN":
      return {
        color: "blue",
        className: "display-logs-stage-run",
      };
    case "TOOL":
      return {
        color: "cyan",
        className: "display-logs-stage-tool",
      };
    default:
      return {
        color: "default",
        className: "display-logs-stage-default",
      };
  }
};

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
        const stageStyle = getStageStyle(message?.stage);
        const isLookupLog = message?.stage === "LOOKUP";
        const rowClassName = isLookupLog ? "display-logs-row-lookup" : "";

        return (
          <div key={message?.timestamp} className={rowClassName}>
            <Row>
              <Col span={4}>
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
                {message?.stage ? (
                  <Tag
                    color={stageStyle.color}
                    className="display-logs-stage-tag"
                  >
                    {isLookupLog && (
                      <SearchOutlined style={{ marginRight: 4 }} />
                    )}
                    {message?.stage}
                  </Tag>
                ) : (
                  <Typography className="display-logs-col">
                    {message?.state}
                  </Typography>
                )}
              </Col>
              <Col span={3}>
                <Typography className="display-logs-col">
                  {message?.component?.prompt_key ||
                    message?.component?.lookup_project ||
                    ""}
                </Typography>
              </Col>
              <Col span={3}>
                <Typography className="display-logs-col">
                  {message?.component?.doc_name || ""}
                </Typography>
              </Col>
              <Col span={10}>
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
