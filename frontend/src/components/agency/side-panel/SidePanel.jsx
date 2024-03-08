import { Tabs } from "antd";

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../../store/session-store";
import { useToolSettingsStore } from "../../../store/tool-settings";
import { ToolSettings } from "../tool-settings/ToolSettings";
import { Tools } from "../tools/Tools";
import "./SidePanel.css";

function SidePanel() {
  const [activeTabKey, setActiveTabKey] = useState("1");
  const [spec, setSpec] = useState({});
  const [isSpecLoading, setSpecLoading] = useState(false);
  const [toolId, setToolId] = useState("");
  const { id } = useParams();
  const { toolSettings } = useToolSettingsStore();
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();

  const items = [
    {
      key: "1",
      label: "Tools",
    },
    {
      key: "2",
      label: "Tool Settings",
      disabled: toolId?.length === 0,
    },
    {
      key: "3",
      label: "Workflow Template",
      disabled: true,
    },
  ];

  const handleTabKey = (key) => {
    setActiveTabKey(key.toString());
  };

  const isObjectEmpty = (obj) => {
    return Object.keys(obj).length === 0;
  };

  useEffect(() => {
    const toolSettingsId = toolSettings?.tool_id;
    if (!toolSettingsId) {
      if (activeTabKey === "2") {
        setActiveTabKey("1");
        setSpec({});
        setToolId("");
      }
      return;
    }

    if (toolSettingsId === toolId) {
      setActiveTabKey("2");
      return;
    }

    if (toolSettingsId !== toolId) {
      setActiveTabKey("2");
      const requestOptions = {
        method: "GET",
        url: `/api/v1/unstract/${sessionDetails?.orgId}/tool_settings_schema/?function_name=${toolSettingsId}&workflow_id=${id}`,
      };
      setSpecLoading(true);
      axiosPrivate(requestOptions)
        .then((res) => {
          if (isObjectEmpty(res?.data?.properties)) {
            // Disable tool settings & switch to Tools tab - when custom tool is selected
            setSpec({});
            setToolId("");
            setActiveTabKey("1");
          } else {
            setToolId(toolSettingsId);
            setSpec(res?.data);
          }
        })
        .catch((err) => {})
        .finally(() => {
          setSpecLoading(false);
        });
    }
  }, [toolSettings]);

  return (
    <div className="sidepanel-layout">
      <div className="sidepanel-tabs">
        <Tabs activeKey={activeTabKey} items={items} onChange={handleTabKey} />
      </div>
      <div className="sidepanel-content">
        {activeTabKey === "1" && <Tools />}
        {activeTabKey === "2" && (
          <ToolSettings spec={spec} isSpecLoading={isSpecLoading} />
        )}
      </div>
    </div>
  );
}

export { SidePanel };
