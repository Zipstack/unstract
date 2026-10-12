import { ArrowLeft, Pencil } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/shims/antd-button";
import { Typography } from "@/components/ui/shims/antd-typography";

import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import "./HeaderTitle.css";

function HeaderTitle() {
  const navigate = useNavigate();
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();

  return (
    <div className="custom-tools-header">
      <div>
        <Button
          size="small"
          type="text"
          onClick={() => navigate(`/${sessionDetails?.orgName}/tools`)}
        >
          <ArrowLeft />
        </Button>
      </div>
      <div>
        <Typography.Text className="custom-tools-name" strong>
          {details?.tool_name}
        </Typography.Text>
        <Button size="small" type="text" icon={<Pencil />} disabled />
      </div>
    </div>
  );
}

export { HeaderTitle };
