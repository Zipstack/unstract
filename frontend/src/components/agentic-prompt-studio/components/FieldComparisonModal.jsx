import PropTypes from "prop-types";
import { useState, useEffect, useMemo } from "react";
import {
  Modal,
  Tabs,
  Checkbox,
  Spin,
  Tag,
  Button,
  Row,
  Col,
  Radio,
  Progress,
  message,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FileTextOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { DiffEditor } from "@monaco-editor/react";

import "./FieldComparisonModal.css";

const FieldComparisonModal = ({ visible, onClose, projectId, documentId }) => {
  const [activeTab, setActiveTab] = useState("fields");
  const [hideEmpty, setHideEmpty] = useState(true);
  const [hideMatches, setHideMatches] = useState(false);
  const [loading, setLoading] = useState(false);
  const [comparison, setComparison] = useState(null);
  const [selectedFieldForTuning, setSelectedFieldForTuning] = useState(null);
  const [tuningStrategy, setTuningStrategy] = useState("multiagent");
  const [tuningProgress, setTuningProgress] = useState(null);

  // Fetch comparison data when modal opens
  useEffect(() => {
    if (visible && projectId && documentId) {
      fetchComparison();
    }
  }, [visible, projectId, documentId]);

  const fetchComparison = async () => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      // Simulate document comparison data
      await new Promise((resolve) => setTimeout(resolve, 800));

      const mockComparison = {
        accuracy: 91.67,
        matches: 11,
        total_fields: 12,
        field_results: {
          invoice_number: {
            extracted: "INV-2025-001",
            verified: "INV-2025-001",
            match: true,
            has_note: false,
            note_text: null,
          },
          invoice_date: {
            extracted: "2025-01-10",
            verified: "2025-01-10",
            match: true,
            has_note: false,
            note_text: null,
          },
          "bill_to.company_name": {
            extracted: "Acme Corporation",
            verified: "Acme Corporation",
            match: true,
            has_note: false,
            note_text: null,
          },
          "bill_to.zip_code": {
            extracted: "9410S",
            verified: "94105",
            match: false,
            has_note: true,
            note_text: "OCR had trouble with the '5' character",
          },
          amount_due: {
            extracted: 1500.0,
            verified: 1500.0,
            match: true,
            has_note: false,
            note_text: null,
          },
        },
      };

      setComparison(mockComparison);
    } catch (error) {
      message.error("Failed to load comparison data");
      console.error("Fetch comparison error:", error);
    } finally {
      setLoading(false);
    }
  };

  // Helper functions
  const renderValue = (value) => {
    if (value === null || value === undefined) return "(empty)";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  };

  const isEmptyValue = (value) => {
    return value === null || value === undefined;
  };

  const getAccuracyColor = (acc) => {
    if (acc >= 90) return "#52c41a";
    if (acc >= 70) return "#faad14";
    return "#ff4d4f";
  };

  // Count empty fields
  const emptyFieldsCount = useMemo(() => {
    if (!comparison) return 0;
    return Object.entries(comparison.field_results).filter(
      ([, result]) =>
        isEmptyValue(result.extracted) && isEmptyValue(result.verified)
    ).length;
  }, [comparison]);

  // Filter fields based on checkbox states
  const filteredFields = useMemo(() => {
    if (!comparison) return [];

    return Object.entries(comparison.field_results).filter(([, result]) => {
      if (
        hideEmpty &&
        isEmptyValue(result.extracted) &&
        isEmptyValue(result.verified)
      ) {
        return false;
      }
      if (hideMatches && result.match) {
        return false;
      }
      return true;
    });
  }, [comparison, hideEmpty, hideMatches]);

  // Reconstruct JSON for diff view
  const reconstructJSON = (fieldResults) => {
    const result = {};
    Object.entries(fieldResults).forEach(([path, value]) => {
      const parts = path.split(/\.|\[|\]/).filter(Boolean);
      let current = result;

      parts.forEach((part, index) => {
        const isLastPart = index === parts.length - 1;
        if (isLastPart) {
          current[part] = value;
        } else {
          if (!current[part]) {
            current[part] = {};
          }
          current = current[part];
        }
      });
    });
    return result;
  };

  const extractedJSON = useMemo(() => {
    if (!comparison) return {};
    const extracted = {};
    Object.entries(comparison.field_results).forEach(([path, result]) => {
      extracted[path] = result.extracted;
    });
    return reconstructJSON(extracted);
  }, [comparison]);

  const verifiedJSON = useMemo(() => {
    if (!comparison) return {};
    const verified = {};
    Object.entries(comparison.field_results).forEach(([path, result]) => {
      verified[path] = result.verified;
    });
    return reconstructJSON(verified);
  }, [comparison]);

  // Handle field selection for tuning
  const handleFieldSelection = (fieldPath) => {
    setSelectedFieldForTuning(fieldPath);
  };

  // Handle tuning
  const handleStartTuning = async () => {
    if (!selectedFieldForTuning) return;

    setTuningProgress({
      status: "running",
      progress: 0,
      message: "Starting tuning...",
    });

    try {
      // TODO: Replace with actual API call
      // Simulate tuning progress
      for (let i = 0; i <= 100; i += 20) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        setTuningProgress({
          status: "running",
          progress: i,
          message: `Tuning field: ${selectedFieldForTuning}`,
        });
      }

      setTuningProgress({
        status: "completed",
        progress: 100,
        message: "Tuning completed successfully",
      });

      message.success("Prompt tuned successfully");

      // Auto-clear after 5 seconds
      setTimeout(() => {
        setTuningProgress(null);
        setSelectedFieldForTuning(null);
      }, 5000);
    } catch (error) {
      setTuningProgress({
        status: "failed",
        progress: 0,
        message: "Tuning failed",
        error: error.message,
      });
      message.error("Failed to tune prompt");
    }
  };

  const tabItems = [
    {
      key: "fields",
      label: "Field Comparison",
      children: (
        <div className="field-comparison-content">
          {filteredFields.length === 0 ? (
            <div className="empty-state">
              No fields to display with current filters.
            </div>
          ) : (
            <div className="fields-list">
              {filteredFields.map(([fieldPath, result]) => (
                <div
                  key={fieldPath}
                  className={`field-item ${
                    result.match ? "match" : "mismatch"
                  }`}
                >
                  <div className="field-header">
                    <div className="field-info">
                      {result.match ? (
                        <CheckCircleOutlined
                          style={{ color: "#52c41a", fontSize: "18px" }}
                        />
                      ) : (
                        <CloseCircleOutlined
                          style={{ color: "#ff4d4f", fontSize: "18px" }}
                        />
                      )}
                      <span className="field-path">{fieldPath}</span>
                    </div>
                    <div className="field-actions">
                      {!result.match && (
                        <Radio
                          checked={selectedFieldForTuning === fieldPath}
                          onChange={() => handleFieldSelection(fieldPath)}
                        >
                          <span style={{ fontSize: "12px" }}>
                            Select for Tuning
                          </span>
                        </Radio>
                      )}
                      <Button
                        size="small"
                        icon={<FileTextOutlined />}
                        type={result.has_note ? "primary" : "default"}
                      >
                        Note
                      </Button>
                      <Tag color={result.match ? "success" : "error"}>
                        {result.match ? "Match" : "Mismatch"}
                      </Tag>
                    </div>
                  </div>
                  <Row gutter={16} style={{ marginTop: "12px" }}>
                    <Col span={12}>
                      <div className="field-label">Extracted</div>
                      <div className="field-value">
                        {renderValue(result.extracted)}
                      </div>
                    </Col>
                    <Col span={12}>
                      <div className="field-label">Verified</div>
                      <div className="field-value">
                        {renderValue(result.verified)}
                      </div>
                    </Col>
                  </Row>
                </div>
              ))}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "json",
      label: "JSON Comparison",
      children: (
        <div style={{ height: "500px" }}>
          <DiffEditor
            original={JSON.stringify(extractedJSON, null, 2)}
            modified={JSON.stringify(verifiedJSON, null, 2)}
            language="json"
            theme="vs-light"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              renderSideBySide: true,
              scrollBeyondLastLine: false,
              fontSize: 13,
              lineNumbers: "on",
              wordWrap: "on",
            }}
            height="100%"
          />
        </div>
      ),
    },
  ];

  return (
    <Modal
      title="Field Comparison"
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="close" onClick={onClose}>
          Close
        </Button>,
      ]}
      width="90%"
      style={{ top: 20 }}
      destroyOnClose
    >
      {loading ? (
        <div style={{ textAlign: "center", padding: "60px" }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} spin />} />
          <p style={{ marginTop: "16px", color: "#666" }}>
            Loading comparison data...
          </p>
        </div>
      ) : comparison ? (
        <>
          {/* Accuracy Summary */}
          <div className="accuracy-summary">
            <div className="accuracy-stat">
              <span className="label">Overall Accuracy:</span>
              <span
                className="value"
                style={{ color: getAccuracyColor(comparison.accuracy) }}
              >
                {comparison.accuracy.toFixed(1)}%
              </span>
            </div>
            <div className="accuracy-detail">
              {comparison.matches} of {comparison.total_fields} fields matched
            </div>
          </div>

          {/* Tuning Panel */}
          {selectedFieldForTuning && (
            <div className="tuning-panel">
              <div className="tuning-header">
                <h4>Prompt Fine-Tuning</h4>
                <div className="tuning-field-info">
                  <span className="label">Selected Field:</span>
                  <code>{selectedFieldForTuning}</code>
                </div>
              </div>
              <div className="tuning-controls">
                <Radio.Group
                  value={tuningStrategy}
                  onChange={(e) => setTuningStrategy(e.target.value)}
                  size="small"
                >
                  <Radio.Button value="single">Single Agent</Radio.Button>
                  <Radio.Button value="multiagent">Multi-Agent</Radio.Button>
                </Radio.Group>
                <Button
                  type="primary"
                  onClick={handleStartTuning}
                  loading={tuningProgress?.status === "running"}
                  disabled={tuningProgress?.status === "running"}
                >
                  Fine-Tune
                </Button>
              </div>
              {tuningProgress && (
                <div className={`tuning-progress ${tuningProgress.status}`}>
                  <Progress
                    percent={tuningProgress.progress}
                    status={
                      tuningProgress.status === "completed"
                        ? "success"
                        : tuningProgress.status === "failed"
                        ? "exception"
                        : "active"
                    }
                  />
                  <p className="tuning-message">{tuningProgress.message}</p>
                  {tuningProgress.error && (
                    <p className="tuning-error">{tuningProgress.error}</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Filter Controls */}
          <div className="filter-controls">
            <Checkbox
              checked={hideEmpty}
              onChange={(e) => setHideEmpty(e.target.checked)}
            >
              Hide {emptyFieldsCount} Empty Field
              {emptyFieldsCount !== 1 ? "s" : ""}
            </Checkbox>
            <Checkbox
              checked={hideMatches}
              onChange={(e) => setHideMatches(e.target.checked)}
            >
              Hide Matches
            </Checkbox>
          </div>

          {/* Tabs */}
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={tabItems}
            style={{ marginTop: "16px" }}
          />
        </>
      ) : (
        <div className="empty-state">No comparison data available</div>
      )}
    </Modal>
  );
};

FieldComparisonModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  projectId: PropTypes.string.isRequired,
  documentId: PropTypes.string.isRequired,
};

export default FieldComparisonModal;
