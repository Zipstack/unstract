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
          <Typography style={{ paddingLeft: "5px" }}>Stage</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Step</Typography>
        </Col>
        <Col className="logs-label-col" span={8}>
          <Typography style={{ paddingLeft: "5px" }}>Message</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Type</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Units</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Cost Value</Typography>
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
