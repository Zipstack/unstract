import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
} from "@ant-design/icons";
import { Col, Row, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import "./GenerateIndex.css";

function GenerateIndex({ isGeneratingIndex, result }) {
  const [text, setText] = useState("");
  const [subText, setSubText] = useState("");

  useEffect(() => {
    if (isGeneratingIndex) {
      setText("Generating Index");
      setSubText("The index will take some time to create.");
      return;
    }

    if (result === "SUCCESS") {
      setText("Successful Index");
      setSubText("Index is ready for inspection.");
      return;
    }

    if (result === "FAILED") {
      setText("Failed to Index");
      setSubText("Please try again");
      return;
    }

    setText("");
    setSubText("");
  }, [isGeneratingIndex]);

  return (
    <div>
      <div>
        <Row>
          <Col span={3}>
            <div>
              {isGeneratingIndex ? (
                <ExclamationCircleFilled className="gen-index-progress gen-index-icon" />
              ) : (
                <>
                  {result === "SUCCESS" ? (
                    <CheckCircleFilled className="gen-index-success gen-index-icon" />
                  ) : (
                    <CloseCircleFilled className="gen-index-fail gen-index-icon" />
                  )}
                </>
              )}
            </div>
          </Col>
          <Col span={21}>
            <Typography.Text className="gen-index-text">{text}</Typography.Text>
          </Col>
        </Row>
      </div>
      <div>
        <Row>
          <Col span={3}></Col>
          <Col span={21}>
            <Typography.Text>{subText}</Typography.Text>
          </Col>
        </Row>
      </div>
    </div>
  );
}

GenerateIndex.propTypes = {
  isGeneratingIndex: PropTypes.bool.isRequired,
  result: PropTypes.string,
};

export { GenerateIndex };
