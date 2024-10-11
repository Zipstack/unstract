import PropTypes from "prop-types";
import Prism from "prismjs";
import { useEffect } from "react";
import TabPane from "antd/es/tabs/TabPane";
import { Tabs } from "antd";
import { JsonViewBody } from "./JsonViewBody";

function JsonView({
  combinedOutput,
  handleTabChange,
  adapterData,
  activeKey,
  selectedProfile,
  llmProfiles,
  isSinglePass,
  isLoading,
}) {
  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput]);

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
        <div className="combined-op-segment"></div>
      </div>
      <div className="combined-op-divider" />
      <JsonViewBody
        activeKey={activeKey}
        selectedProfile={selectedProfile}
        llmProfiles={llmProfiles}
        combinedOutput={combinedOutput}
        isLoading={isLoading}
      />
      <div className="gap" />
    </div>
  );
}

JsonView.propTypes = {
  combinedOutput: PropTypes.object.isRequired,
  handleTabChange: PropTypes.func,
  adapterData: PropTypes.array,
  selectedProfile: PropTypes.string,
  llmProfiles: PropTypes.array,
  activeKey: PropTypes.string,
  isSinglePass: PropTypes.bool,
  isLoading: PropTypes.bool.isRequired,
};

export { JsonView };
