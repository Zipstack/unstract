import { Typography } from "antd";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { ToolSettings } from "../tool-settings/ToolSettings";
import "./SidePanel.css";

function SidePanel() {
  const [spec, setSpec] = useState({});
  const [isSpecLoading, setSpecLoading] = useState(false);
  const [toolId, setToolId] = useState("");
  const { id } = useParams();
  const { toolSettings } = useToolSettingsStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();

  const isObjectEmpty = (obj) => {
    return Object.keys(obj).length === 0;
  };

  useEffect(() => {
    const toolSettingsId = toolSettings?.tool_id;

    if (!toolSettingsId) {
      setSpec({});
      setToolId("");
      return;
    }

    if (toolSettingsId === toolId) {
      return;
    }

    if (toolSettingsId !== toolId) {
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_settings_schema/?function_name=${toolSettingsId}&workflow_id=${id}`,
      };
      setSpecLoading(true);
      axiosPrivate(requestOptions)
        .then((res) => {
          if (isObjectEmpty(res?.data?.properties)) {
            // Prompt Studio tools don't have configurable settings via this interface
            setSpec({});
            setToolId(toolSettingsId);
          } else {
            setToolId(toolSettingsId);
            setSpec(res?.data);
          }
        })
        .catch((err) => {
          // Handle API errors for tool settings schema
          setSpec({});
          setToolId("");
        })
        .finally(() => {
          setSpecLoading(false);
        });
    }
  }, [toolSettings]);

  return (
    <div className="sidepanel-layout">
      <div className="sidepanel-header">
        <Typography.Title level={4}>Tool Settings</Typography.Title>
      </div>
      <div className="sidepanel-content">
        <ToolSettings spec={spec} isSpecLoading={isSpecLoading} />
      </div>
    </div>
  );
}

export { SidePanel };
