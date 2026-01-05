import PropTypes from "prop-types";
import { Tag, Space } from "antd";
import { CheckCircleOutlined, ThunderboltOutlined } from "@ant-design/icons";

import { ProfileInfoBar } from "../profile-info-bar/ProfileInfoBar";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function JsonViewBody({
  activeKey,
  selectedProfile,
  llmProfiles,
  combinedOutput,
  isLoading,
  isEnriched,
  enrichmentMetadata,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  return (
    <>
      {activeKey !== "0" && (
        <ProfileInfoBar profileId={selectedProfile} profiles={llmProfiles} />
      )}
      {isEnriched && enrichmentMetadata && (
        <div className="enrichment-info-bar">
          <Space size="small">
            <Tag icon={<ThunderboltOutlined />} color="success">
              Enriched with Look-Ups
            </Tag>
            <Tag color="blue">
              {enrichmentMetadata.lookups_executed} Look-Up
              {enrichmentMetadata.lookups_executed !== 1 ? "s" : ""} executed
            </Tag>
            {enrichmentMetadata.lookup_details?.map((detail, idx) => (
              <Tag
                key={idx}
                icon={
                  detail.status === "success" ? (
                    <CheckCircleOutlined />
                  ) : undefined
                }
                color={
                  detail.status === "success"
                    ? "green"
                    : detail.status === "error"
                    ? "red"
                    : "default"
                }
              >
                {detail.project_name}
              </Tag>
            ))}
          </Space>
        </div>
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
  isEnriched: PropTypes.bool,
  enrichmentMetadata: PropTypes.object,
};

export { JsonViewBody };
