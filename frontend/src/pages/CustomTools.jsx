import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { ListOfTools } from "../components/custom-tools/list-of-tools/ListOfTools";

const TAB_OPTIONS = ["Projects", "Look-Ups"];

function CustomTools() {
  const location = useLocation();
  const [LookupListComp, setLookupListComp] = useState(null);
  const [activeTab, setActiveTab] = useState(
    location.state?.activeTab || "Projects",
  );

  useEffect(() => {
    import("../plugins/lookup-studio")
      .then((mod) => setLookupListComp(() => mod.LookupList))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (location.state?.activeTab) {
      setActiveTab(location.state.activeTab);
    }
  }, [location.state?.activeTab]);

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
