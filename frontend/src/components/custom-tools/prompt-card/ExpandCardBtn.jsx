import { FullscreenExitOutlined, FullscreenOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

function ExpandCardBtn({ expandCard, setExpandCard }) {
  const [icon, setIcon] = useState(null);
  const [tooltip, setTooltip] = useState("");

  useEffect(() => {
    if (expandCard) {
      setIcon(<FullscreenExitOutlined className="prompt-card-actions-head" />);
      setTooltip("Collapse");
    } else {
      setIcon(<FullscreenOutlined className="prompt-card-actions-head" />);
      setTooltip("Expand");
    }
  }, [expandCard]);

  const handleClick = () => {
    setExpandCard(!expandCard);
  };

  return (
    <Tooltip title={tooltip}>
      <Button
        size="small"
        type="text"
        className="prompt-card-action-button"
        onClick={handleClick}
      >
        {icon}
      </Button>
    </Tooltip>
  );
}

ExpandCardBtn.propTypes = {
  expandCard: PropTypes.bool.isRequired,
  setExpandCard: PropTypes.func.isRequired,
};

export { ExpandCardBtn };
