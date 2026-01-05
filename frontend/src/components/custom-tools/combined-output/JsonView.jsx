import PropTypes from "prop-types";
import Prism from "prismjs";
import { useEffect, useState } from "react";
import TabPane from "antd/es/tabs/TabPane";
import { Tabs, Button, Tooltip, Badge } from "antd";
import { ThunderboltOutlined, CheckCircleOutlined } from "@ant-design/icons";

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
  onEnrichWithLookups,
  isEnriching,
  enrichmentResult,
  hasLinkedLookups,
}) {
  const [showEnriched, setShowEnriched] = useState(false);

  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput, enrichmentResult, showEnriched]);

  // Determine what output to display
  const displayOutput =
    showEnriched && enrichmentResult?.enriched_data
      ? enrichmentResult.enriched_data
      : combinedOutput;

  const handleEnrichClick = () => {
    if (enrichmentResult) {
      // Toggle between original and enriched view
      setShowEnriched(!showEnriched);
    } else if (onEnrichWithLookups) {
      // Trigger enrichment
      onEnrichWithLookups();
    }
  };

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
          {hasLinkedLookups && onEnrichWithLookups && (
            <Tooltip
              title={
                enrichmentResult
                  ? showEnriched
                    ? "Show original output"
                    : "Show enriched output"
                  : "Enrich output with linked Look-Ups"
              }
            >
              <Badge
                dot={enrichmentResult && !showEnriched}
                status="success"
                offset={[-2, 2]}
              >
                <Button
                  type={showEnriched ? "primary" : "default"}
                  size="small"
                  icon={
                    enrichmentResult ? (
                      <CheckCircleOutlined />
                    ) : (
                      <ThunderboltOutlined />
                    )
                  }
                  loading={isEnriching}
                  onClick={handleEnrichClick}
                  disabled={
                    isLoading || Object.keys(combinedOutput).length === 0
                  }
                >
                  {enrichmentResult
                    ? showEnriched
                      ? "Show Original"
                      : "Show Enriched"
                    : "Enrich with Look-Ups"}
                </Button>
              </Badge>
            </Tooltip>
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
        isEnriched={showEnriched}
        enrichmentMetadata={enrichmentResult?._lookup_metadata}
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
  onEnrichWithLookups: PropTypes.func,
  isEnriching: PropTypes.bool,
  enrichmentResult: PropTypes.object,
  hasLinkedLookups: PropTypes.bool,
};

export { JsonView };
