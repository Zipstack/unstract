import { Col, Row, Typography } from "antd";

import "../../agency/logs-label/LogsLabel.css";

function LogsLabel() {
  return (
    <div className="pl-5">
      <Row className="logs-label-row">
        <Col className="logs-label-col" span={5}>
          <Typography>Time</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Level</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">State</Typography>
        </Col>
        <Col className="logs-label-col" span={3}>
          <Typography className="pl-5">Prompt Key</Typography>
        </Col>
        <Col className="logs-label-col" span={3}>
          <Typography className="pl-5">Document Name</Typography>
        </Col>
        <Col className="logs-label-col" span={8}>
          <Typography className="pl-5">Message</Typography>
        </Col>
      </Row>
    </div>
  );
}

export { LogsLabel };
