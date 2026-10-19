import { CircleAlert, CircleCheck, CircleX } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Col, Row } from "@/components/ui/shims/antd-layout";
import { Typography } from "@/components/ui/shims/antd-typography";

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
                <CircleAlert className="gen-index-progress gen-index-icon" />
              ) : (
                <>
                  {result === "SUCCESS" ? (
                    <CircleCheck className="gen-index-success gen-index-icon" />
                  ) : (
                    <CircleX className="gen-index-fail gen-index-icon" />
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
