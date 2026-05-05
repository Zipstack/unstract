import { Tabs } from "antd";
import TabPane from "antd/es/tabs/TabPane";
import Prism from "prismjs";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { JsonViewBody } from "./JsonViewBody";

let EnrichedOutputToggle;
try {
  const mod = await import(
    "../../../plugins/lookup-enriched-toggle/EnrichedOutputToggle"
  );
  EnrichedOutputToggle = mod.EnrichedOutputToggle;
} catch {
  // The component will remain undefined if it is not available
}

function JsonView({
  combinedOutput,
  enrichedOutput,
  handleTabChange,
  adapterData,
  activeKey,
  selectedProfile,
  llmProfiles,
  isSinglePass,
  isLoading,
}) {
  const [activeView, setActiveView] = useState("Raw");

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput, enrichedOutput, activeView]);

  useEffect(() => {
    if (!enrichedOutput || Object.keys(enrichedOutput).length === 0) {
      setActiveView("Raw");
    }
  }, [enrichedOutput]);

  const displayOutput =
    activeView === "Enriched" &&
    enrichedOutput &&
    Object.keys(enrichedOutput).length > 0
      ? enrichedOutput
      : combinedOutput;

  return (
    <div className="combined-op-layout">
      <div className="combined-op-header">
        <Tabs activeKey={activeKey} onChange={handleTabChange} moreIcon={<></>}>
          {!isSinglePass && (
            <TabPane tab={<span>Default</span>} key={"0"}></TabPane>
          )}
          {adapterData.map((adapter) => (
            <TabPane
              tab={<span>{adapter?.llm_model || adapter?.profile_name}</span>}
              key={adapter?.profile_id}
            />
          ))}
        </Tabs>
        <div className="combined-op-segment">
          {EnrichedOutputToggle && (
            <EnrichedOutputToggle
              activeView={activeView}
              onChange={setActiveView}
              hasEnrichedData={
                !!(enrichedOutput && Object.keys(enrichedOutput).length > 0)
              }
            />
          )}
        </div>
      </div>
      <div className="combined-op-divider" />
      <JsonViewBody
        activeKey={activeKey}
        selectedProfile={selectedProfile}
        llmProfiles={llmProfiles}
        combinedOutput={displayOutput}
        isLoading={isLoading}
      />
      <div className="gap" />
    </div>
  );
}

JsonView.propTypes = {
  combinedOutput: PropTypes.object.isRequired,
  enrichedOutput: PropTypes.object,
  handleTabChange: PropTypes.func,
  adapterData: PropTypes.array,
  selectedProfile: PropTypes.string,
  llmProfiles: PropTypes.array,
  activeKey: PropTypes.string,
  isSinglePass: PropTypes.bool,
  isLoading: PropTypes.bool.isRequired,
};

export { JsonView };
