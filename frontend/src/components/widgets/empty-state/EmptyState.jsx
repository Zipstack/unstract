import { Plus } from "lucide-react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/shims/antd-button";
import { Space } from "@/components/ui/shims/antd-layout";
import { Typography } from "@/components/ui/shims/antd-typography";

import { EmptyPlaceholder } from "../../../assets";

function EmptyState({ text, btnText, handleClick }) {
  return (
    <div className="display-flex-center-h-and-v" data-testid="empty-state">
      <Space direction="vertical" className="display-flex-align-center">
        <EmptyPlaceholder />
        <div>
          <div className="display-flex-center">
            <Typography.Text type="secondary">{text}</Typography.Text>
          </div>
          {btnText?.length > 0 && (
            <div className="display-flex-center">
              <Button
                type="link"
                icon={<Plus />}
                data-testid="empty-state-action-btn"
                onClick={handleClick}
              >
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
  text: PropTypes.node.isRequired,
  btnText: PropTypes.string,
  handleClick: PropTypes.func,
};

export { EmptyState };
