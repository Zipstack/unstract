import { Col, Row, Typography } from "antd";

import "../../agency/logs-label/LogsLabel.css";

function LogsLabel() {
  return (
    <div className="pl-5">
      <Row className="logs-label-row">
        <Col className="logs-label-col" span={3}>
          <Typography>Time</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>Level</Typography>
        </Col>
        <Col className="logs-label-col" span={2}>
          <Typography style={{ paddingLeft: "5px" }}>State</Typography>
        </Col>
        <Col className="logs-label-col" span={16}>
          <Typography style={{ paddingLeft: "5px" }}>Message</Typography>
        </Col>
      </Row>
    </div>
  );
}

export { LogsLabel };
