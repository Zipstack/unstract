import { Col, Row, Typography } from "antd";

import "./LogsLabel.css";
import { useLocation } from "react-router-dom";
import { isSubPage } from "../../../helpers/GetStaticData";

function LogsLabel() {
  const location = useLocation(); // Get the current route location
  const isWorkflowSubPage = isSubPage("workflows", location.pathname);
  const isPromptStudioPage = isSubPage("tools", location.pathname);

  return (
    <div className="pl-5">
      <Row className="logs-label-row">
        <Col className="logs-label-col" span={2}>
          <Typography>Time</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Level</Typography>
        </Col>
        <Col className="logs-label-col" span={3}>
          <Typography className="pl-5">Type</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Stage</Typography>
        </Col>
        {isWorkflowSubPage && (
          <>
            <Col className="logs-label-col" span={2}>
              <Typography className="pl-5">Step</Typography>
            </Col>
            <Col className="logs-label-col" span={2}>
              <Typography className="pl-5">State</Typography>
            </Col>
          </>
        )}
        {isPromptStudioPage && (
          <>
            <Col className="logs-label-col" span={2}>
              <Typography className="pl-5">Prompt Key</Typography>
            </Col>
            <Col className="logs-label-col" span={2}>
              <Typography className="pl-5">Doc Name</Typography>
            </Col>
          </>
        )}
        <Col className="logs-label-col" flex="auto">
          <Typography className="pl-5">Message</Typography>
        </Col>
      </Row>
    </div>
  );
}

export { LogsLabel };
