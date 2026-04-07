import { useEffect, useState } from "react";

import { ListOfTools } from "../components/custom-tools/list-of-tools/ListOfTools";

const TAB_OPTIONS = ["Projects", "Look-Ups"];

function CustomTools() {
  const [LookupListComp, setLookupListComp] = useState(null);
  const [activeTab, setActiveTab] = useState("Projects");

  useEffect(() => {
    import("../plugins/lookup-studio")
      .then((mod) => setLookupListComp(() => mod.LookupList))
      .catch(() => {});
  }, []);

  // No lookup plugin = just render projects list (OSS mode)
  if (!LookupListComp) {
    return <ListOfTools />;
  }

  const tabProps = {
    segmentOptions: TAB_OPTIONS,
    segmentValue: activeTab,
    onSegmentChange: setActiveTab,
  };

  return activeTab === "Projects" ? (
    <ListOfTools {...tabProps} />
  ) : (
    <LookupListComp {...tabProps} />
  );
}

export { CustomTools };
