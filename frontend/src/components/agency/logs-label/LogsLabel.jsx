import { Col, Row, Typography } from "antd";

import "./LogsLabel.css";

function LogsLabel() {
  return (
    <div className="pl-5">
      <Row className="logs-label-row">
        <Col className="logs-label-col" span={2}>
          <Typography>Time</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Stage</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Step</Typography>
        </Col>
        <Col className="logs-label-col" span={8}>
          <Typography className="pl-5">Message</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Cost Type</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Cost Units</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Cost Value</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography className="pl-5">Iteration</Typography>
        </Col>
        <Col style={{}} span={2}>
          <Typography className="pl-5">Iteration Total</Typography>
        </Col>
      </Row>
    </div>
  );
}

export { LogsLabel };
