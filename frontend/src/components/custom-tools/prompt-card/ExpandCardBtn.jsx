import { Maximize, Minimize } from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/shims/antd-button";
import { Tooltip } from "@/components/ui/shims/antd-overlays";

function ExpandCardBtn({ expandCard, setExpandCard, testId }) {
  const [icon, setIcon] = useState(null);
  const [tooltip, setTooltip] = useState("");

  useEffect(() => {
    if (expandCard) {
      setIcon(<Minimize className="prompt-card-actions-head" />);
      setTooltip("Collapse");
    } else {
      setIcon(<Maximize className="prompt-card-actions-head" />);
      setTooltip("Expand");
    }
  }, [expandCard]);

  const handleClick = () => {
    setExpandCard(!expandCard);
  };

  return (
    <Tooltip title={tooltip}>
      <Button
        data-testid={testId}
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
  testId: PropTypes.string,
};

export { ExpandCardBtn };
