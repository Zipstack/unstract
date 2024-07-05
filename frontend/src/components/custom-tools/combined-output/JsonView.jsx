import PropTypes from "prop-types";
import Prism from "prismjs";
import { useEffect } from "react";
import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";
import TabPane from "antd/es/tabs/TabPane";
import { Tabs } from "antd";

function JsonView({
  combinedOutput,
  handleTabChange,
  adapterData,
  activeKey,
  selectedProfile,
  llmProfiles,
}) {
  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput]);

  return (
    <div className="combined-op-layout">
      <div className="combined-op-header">
        <Tabs activeKey={activeKey} onChange={handleTabChange} moreIcon={<></>}>
          <TabPane tab={<span>Default</span>} key={"0"}></TabPane>
          {adapterData.map((adapter, index) => (
            <TabPane
              tab={<span>{adapter.llm_model}</span>}
              key={(index + 1)?.toString()}
            />
          ))}
        </Tabs>
        <div className="combined-op-segment"></div>
      </div>
      <div className="combined-op-divider" />
      <ProfileInfoBar profileId={selectedProfile} profiles={llmProfiles} />
      <div className="combined-op-body code-snippet">
        {combinedOutput && (
          <pre className="line-numbers width-100">
            <code className="language-javascript width-100">
              {JSON.stringify(combinedOutput, null, 2)}
            </code>
          </pre>
        )}
      </div>
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
};

export { JsonView };
