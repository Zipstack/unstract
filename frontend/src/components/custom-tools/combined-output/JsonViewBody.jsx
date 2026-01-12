import PropTypes from "prop-types";

import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function JsonViewBody({
  activeKey,
  selectedProfile,
  llmProfiles,
  combinedOutput,
  isLoading,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  return (
    <>
      {activeKey !== "0" && (
        <ProfileInfoBar profileId={selectedProfile} profiles={llmProfiles} />
      )}
      <div className="combined-op-body code-snippet">
        {combinedOutput && (
          <pre className="line-numbers width-100">
            <code className="language-javascript width-100">
              {JSON.stringify(combinedOutput, null, 2)}
            </code>
          </pre>
        )}
      </div>
    </>
  );
}

JsonViewBody.propTypes = {
  activeKey: PropTypes.string.isRequired,
  selectedProfile: PropTypes.string,
  llmProfiles: PropTypes.string,
  combinedOutput: PropTypes.object,
  isLoading: PropTypes.bool.isRequired,
};

export { JsonViewBody };
