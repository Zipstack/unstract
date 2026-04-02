import { PlusOutlined } from "@ant-design/icons";
import { Button } from "antd";
import PropTypes from "prop-types";

import "./Footer.css";
import { promptType } from "../../../helpers/GetStaticData";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { FooterLayout } from "../footer-layout/FooterLayout";

function Footer({ activeKey, addPromptInstance }) {
  const { isPublicSource } = useCustomToolStore();
  if (activeKey === "1") {
    return (
      <FooterLayout>
        <div className="tool-ide-main-footer">
          <div>
            <Button
              type="link"
              icon={<PlusOutlined />}
              onClick={() => addPromptInstance(promptType.notes)}
              disabled={isPublicSource}
            >
              Notes
            </Button>
          </div>
          <div>
            <Button
              type="link"
              icon={<PlusOutlined />}
              onClick={() => addPromptInstance(promptType.prompt)}
              disabled={isPublicSource}
            >
              Prompt
            </Button>
          </div>
        </div>
      </FooterLayout>
    );
  }

  return <></>;
}

Footer.propTypes = {
  activeKey: PropTypes.string.isRequired,
  addPromptInstance: PropTypes.func.isRequired,
};

export { Footer };
