import PropTypes from "prop-types";
import { useState, useEffect } from "react";
import { Card, Button, Spin, message } from "antd";
import { LoadingOutlined, ReloadOutlined } from "@ant-design/icons";

const AccuracyOverviewPanel = ({ projectId }) => {
  const [accuracy, setAccuracy] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  useEffect(() => {
    if (projectId) {
      fetchAccuracy();
    }
  }, [projectId]);

  const fetchAccuracy = async () => {
    setLoading(true);
    try {
      // TODO: Replace with actual API call
      await new Promise((resolve) => setTimeout(resolve, 600));

      const mockAccuracy = {
        accuracy: 91.67,
        documents_compared: 12,
        documents_total: 15,
      };

      setAccuracy(mockAccuracy);
    } catch (error) {
      message.error("Failed to load accuracy metrics");
      console.error("Fetch accuracy error:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      await fetchAccuracy();

      if (accuracy && accuracy.documents_compared > 0) {
        message.success("Accuracy recalculated successfully");
      } else {
        message.error(
          "No extraction data available to calculate accuracy. Run extraction on documents with verified data first."
        );
      }
    } catch (error) {
      message.error("Failed to recalculate accuracy");
      console.error("Recalculate accuracy error:", error);
    } finally {
      setRecalculating(false);
    }
  };

  const getAccuracyColor = (acc) => {
    if (acc >= 90) return "#52c41a";
    if (acc >= 70) return "#faad14";
    return "#ff4d4f";
  };

  const getAccuracyBgColor = (acc) => {
    if (acc >= 90)
      return { backgroundColor: "#f6ffed", borderColor: "#b7eb8f" };
    if (acc >= 70)
      return { backgroundColor: "#fffbe6", borderColor: "#ffe58f" };
    return { backgroundColor: "#fff1f0", borderColor: "#ffccc7" };
  };

  if (loading) {
    return (
      <Card style={{ marginBottom: "24px" }}>
        <div style={{ textAlign: "center", padding: "20px" }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          <p style={{ marginTop: "12px", color: "#666", fontSize: "14px" }}>
            Loading accuracy metrics...
          </p>
        </div>
      </Card>
    );
  }

  // No data to compare
  if (accuracy && accuracy.documents_compared === 0) {
    return (
      <Card style={{ marginBottom: "24px", backgroundColor: "#fafafa" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h3
              style={{ fontSize: "16px", fontWeight: 500, margin: "0 0 8px 0" }}
            >
              Project Accuracy
            </h3>
            <p style={{ fontSize: "14px", color: "#666", margin: 0 }}>
              No accuracy data available. Run extraction on documents with
              verified data to see metrics.
            </p>
          </div>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={handleRecalculate}
            loading={recalculating}
          >
            Calculate Accuracy
          </Button>
        </div>
      </Card>
    );
  }

  if (!accuracy) return null;

  const accuracyPercent = Math.round(accuracy.accuracy * 10) / 10;
  const bgStyle = getAccuracyBgColor(accuracyPercent);

  return (
    <Card
      style={{
        marginBottom: "24px",
        ...bgStyle,
        border: `1px solid ${bgStyle.borderColor}`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ flex: 1 }}>
          <h3
            style={{ fontSize: "16px", fontWeight: 500, margin: "0 0 12px 0" }}
          >
            Project Accuracy
          </h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: "24px" }}>
            <div>
              <span
                style={{
                  fontSize: "48px",
                  fontWeight: "bold",
                  color: getAccuracyColor(accuracyPercent),
                }}
              >
                {accuracyPercent}%
              </span>
            </div>
            <div style={{ fontSize: "14px", color: "#666" }}>
              <p style={{ margin: 0 }}>
                {accuracy.documents_compared} of {accuracy.documents_total}{" "}
                documents compared
              </p>
            </div>
          </div>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={handleRecalculate}
          loading={recalculating}
        >
          Recalculate
        </Button>
      </div>
    </Card>
  );
};

AccuracyOverviewPanel.propTypes = {
  projectId: PropTypes.string.isRequired,
};

export default AccuracyOverviewPanel;
