import { PlusOutlined } from "@ant-design/icons";
import { Button, Space, Typography } from "antd";
import PropTypes from "prop-types";

import { EmptyPlaceholder } from "../../../assets";

function EmptyState({ text, btnText, handleClick }) {
  return (
    <div className="display-flex-center-h-and-v">
      <Space direction="vertical" className="display-flex-align-center">
        <EmptyPlaceholder />
        <div>
          <div className="display-flex-center">
            <Typography.Text type="secondary">{text}</Typography.Text>
          </div>
          {btnText?.length > 0 && (
            <div className="display-flex-center">
              <Button type="link" icon={<PlusOutlined />} onClick={handleClick}>
                {btnText}
              </Button>
            </div>
          )}
        </div>
      </Space>
    </div>
  );
}

EmptyState.propTypes = {
  text: PropTypes.string.isRequired,
  btnText: PropTypes.string,
  handleClick: PropTypes.func,
};

export { EmptyState };
