import { Typography } from "antd";
import PropTypes from "prop-types";
import { InfoCircleFilled } from "@ant-design/icons";

import { displayPromptResult } from "../../../helpers/GetStaticData";
import "./PromptCard.css";

function DisplayPromptResult({ output }) {
  if (!output) {
    return (
      <Typography.Text className="prompt-not-ran">
        <span>
          <InfoCircleFilled className="info-circle-colored" />
        </span>{" "}
        Yet to run
      </Typography.Text>
    );
  }

  return (
    <Typography.Paragraph className="prompt-card-display-output font-size-12">
      <div>{displayPromptResult(output, true)}</div>
    </Typography.Paragraph>
  );
}

DisplayPromptResult.propTypes = {
  output: PropTypes.any,
};

export { DisplayPromptResult };
