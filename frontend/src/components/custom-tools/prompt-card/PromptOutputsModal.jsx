import { Col, Image, Modal, Row, Typography } from "antd";
import PropTypes from "prop-types";

import { DisplayPromptResult } from "./DisplayPromptResult";
import { TABLE_ENFORCE_TYPE, RECORD_ENFORCE_TYPE } from "./constants";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePromptOutput from "../../../hooks/usePromptOutput";

let TableOutput;
try {
  TableOutput = require("../../../plugins/prompt-card/TableOutput").TableOutput;
} catch {
  // The component will remain null of it is not available
}

function PromptOutputsModal({
  open,
  setOpen,
  promptId,
  llmProfiles,
  enforceType,
  displayLlmProfile,
  promptOutputs,
  promptRunStatus,
}) {
  const { singlePassExtractMode, selectedDoc } = useCustomToolStore();
  const { generatePromptOutputKey } = usePromptOutput();

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      centered
      maskClosable={false}
      footer={null}
      width={1600}
    >
      <SpaceWrapper>
        <Typography.Text
          className="prompt-output-pad prompt-output-title"
          strong
        >
          Prompt Results
        </Typography.Text>
        <Row style={{ height: "85vh" }}>
          {llmProfiles.map((profile, index) => {
            const profileId = profile?.profile_id;
            const docId = selectedDoc?.document_id;
            const promptOutputKey = generatePromptOutputKey(
              promptId,
              docId,
              profileId,
              singlePassExtractMode,
              true
            );
            const promptOutputData = promptOutputs[promptOutputKey];
            return (
              <Col
                className={`overflow-hidden height-100 prompt-output-pad ${
                  index < llmProfiles?.length - 1 && "border-right-grey"
                }`}
                key={profileId}
                span={24 / llmProfiles?.length}
              >
                <div className="flex-dir-col">
                  <div>
                    {displayLlmProfile && (
                      <div className="llm-info prompt-output-llm-bg">
                        <Image
                          src={profile?.icon}
                          width={15}
                          height={15}
                          preview={false}
                          className="prompt-card-llm-icon"
                        />
                        <Typography.Text className="prompt-card-llm-title">
                          {profile?.conf?.LLM}
                        </Typography.Text>
                      </div>
                    )}
                  </div>
                  <div className="flex-1 overflow-y-auto pad-top-10">
                    {(enforceType === TABLE_ENFORCE_TYPE ||
                      enforceType === RECORD_ENFORCE_TYPE) &&
                    TableOutput ? (
                      <TableOutput
                        output={promptOutputData?.output}
                        pagination={10}
                      />
                    ) : (
                      <DisplayPromptResult
                        output={promptOutputData?.output}
                        profileId={profileId}
                        docId={docId}
                        promptRunStatus={promptRunStatus}
                      />
                    )}
                  </div>
                </div>
              </Col>
            );
          })}
        </Row>
      </SpaceWrapper>
    </Modal>
  );
}

PromptOutputsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  promptId: PropTypes.string.isRequired,
  llmProfiles: PropTypes.array.isRequired,
  enforceType: PropTypes.string,
  displayLlmProfile: PropTypes.bool.isRequired,
  promptOutputs: PropTypes.object.isRequired,
  promptRunStatus: PropTypes.object.isRequired,
};

export { PromptOutputsModal };
