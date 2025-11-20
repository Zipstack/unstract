import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Modal, Select, Spin, Button, Row, Col, message } from "antd";
import { SwapOutlined, LoadingOutlined } from "@ant-design/icons";
import ReactDiffViewer from "react-diff-viewer-continued";

import { useMockApi } from "../hooks/useMockApi";

const ComparePromptsModal = ({
  visible,
  onClose,
  projectId,
  currentVersion,
  compareVersion,
}) => {
  const [leftVersion, setLeftVersion] = useState(
    compareVersion || currentVersion - 1
  );
  const [rightVersion, setRightVersion] = useState(currentVersion);
  const [allPrompts, setAllPrompts] = useState([]);
  const [leftPrompt, setLeftPrompt] = useState(null);
  const [rightPrompt, setRightPrompt] = useState(null);
  const [loading, setLoading] = useState(false);
  const { getPrompts } = useMockApi();

  // Update versions when compareVersion prop changes
  useEffect(() => {
    if (compareVersion) {
      setLeftVersion(compareVersion);
      setRightVersion(currentVersion);
    }
  }, [compareVersion, currentVersion]);

  // Fetch all prompts when modal opens
  useEffect(() => {
    if (visible && projectId) {
      fetchAllPrompts();
    }
  }, [visible, projectId]);

  // Fetch specific versions when versions change
  useEffect(() => {
    if (visible && allPrompts.length > 0) {
      fetchPromptVersions();
    }
  }, [visible, leftVersion, rightVersion, allPrompts]);

  const fetchAllPrompts = async () => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      const data = await getPrompts(projectId);
      setAllPrompts(data);
    } catch (error) {
      message.error("Failed to load prompt history");
      console.error("Fetch prompts error:", error);
    } finally {
      setLoading(false);
    }
  };

  const fetchPromptVersions = () => {
    // Find prompts by version from allPrompts
    const left = allPrompts.find((p) => p.version === leftVersion);
    const right = allPrompts.find((p) => p.version === rightVersion);

    setLeftPrompt(left);
    setRightPrompt(right);
  };

  const handleLeftVersionChange = (version) => {
    setLeftVersion(version);
  };

  const handleRightVersionChange = (version) => {
    setRightVersion(version);
  };

  return (
    <Modal
      title={
        <span>
          <SwapOutlined style={{ marginRight: "8px" }} />
          Compare Prompt Versions
        </span>
      }
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          Close
        </Button>,
      ]}
      width="95%"
      style={{ top: 20 }}
      destroyOnClose
    >
      <Row gutter={16} style={{ marginBottom: "16px" }}>
        <Col span={12}>
          <div style={{ marginBottom: "8px", fontWeight: 500 }}>
            Left Version
          </div>
          <Select
            value={leftVersion}
            onChange={handleLeftVersionChange}
            style={{ width: "100%" }}
            placeholder="Select left version"
          >
            {allPrompts.map((p) => (
              <Select.Option key={p.id} value={p.version}>
                v{p.version} - {p.short_desc || "No description"}
              </Select.Option>
            ))}
          </Select>
        </Col>
        <Col span={12}>
          <div style={{ marginBottom: "8px", fontWeight: 500 }}>
            Right Version
          </div>
          <Select
            value={rightVersion}
            onChange={handleRightVersionChange}
            style={{ width: "100%" }}
            placeholder="Select right version"
          >
            {allPrompts.map((p) => (
              <Select.Option key={p.id} value={p.version}>
                v{p.version} - {p.short_desc || "No description"}
              </Select.Option>
            ))}
          </Select>
        </Col>
      </Row>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px" }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          <p style={{ marginTop: "16px", color: "#666" }}>Loading prompts...</p>
        </div>
      ) : leftPrompt && rightPrompt ? (
        <div
          style={{
            border: "1px solid #d9d9d9",
            borderRadius: "4px",
            overflow: "auto",
            maxHeight: "60vh",
          }}
        >
          <ReactDiffViewer
            oldValue={leftPrompt.prompt_text}
            newValue={rightPrompt.prompt_text}
            splitView={true}
            showDiffOnly={false}
            useDarkTheme={false}
            leftTitle={`v${leftVersion} - ${
              leftPrompt.short_desc || "No description"
            }`}
            rightTitle={`v${rightVersion} - ${
              rightPrompt.short_desc || "No description"
            }`}
            styles={{
              variables: {
                light: {
                  diffViewerBackground: "#fff",
                  addedBackground: "#e6ffed",
                  addedColor: "#24292e",
                  removedBackground: "#ffeef0",
                  removedColor: "#24292e",
                  wordAddedBackground: "#acf2bd",
                  wordRemovedBackground: "#fdb8c0",
                  addedGutterBackground: "#cdffd8",
                  removedGutterBackground: "#ffdce0",
                  gutterBackground: "#f6f8fa",
                  gutterBackgroundDark: "#f3f4f6",
                  highlightBackground: "#fffbdd",
                  highlightGutterBackground: "#fff5b1",
                },
              },
            }}
          />
        </div>
      ) : (
        <p style={{ textAlign: "center", padding: "40px", color: "#666" }}>
          Unable to load prompt versions
        </p>
      )}
    </Modal>
  );
};

ComparePromptsModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  projectId: PropTypes.string.isRequired,
  currentVersion: PropTypes.number.isRequired,
  compareVersion: PropTypes.number,
};

export default ComparePromptsModal;
