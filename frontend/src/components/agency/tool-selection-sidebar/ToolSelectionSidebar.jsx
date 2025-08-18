import { Button, Input, Typography, List, Card, Tag } from "antd";
import { SearchOutlined, FileTextOutlined } from "@ant-design/icons";
import { useState, useEffect } from "react";
import PropTypes from "prop-types";

import "./ToolSelectionSidebar.css";
import { ToolIcon } from "../tool-icon/ToolIcon";

function ToolSelectionSidebar({
  visible,
  onClose,
  tools,
  selectedTool,
  onToolSelect,
  onSave,
}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [tempSelectedTool, setTempSelectedTool] = useState(selectedTool);
  const [hasChanges, setHasChanges] = useState(false);

  // Sync tempSelectedTool when sidebar becomes visible or selectedTool changes
  useEffect(() => {
    if (visible) {
      setTempSelectedTool(selectedTool);
      setHasChanges(false);
      setSearchTerm("");
    }
  }, [visible, selectedTool]);

  // Filter tools based on search term
  const filteredTools = tools.filter(
    (tool) =>
      tool.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tool.description?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleToolSelect = (toolFunctionName) => {
    setTempSelectedTool(toolFunctionName);
    setHasChanges(toolFunctionName !== selectedTool);
  };

  const handleSave = () => {
    if (hasChanges && tempSelectedTool) {
      onToolSelect(tempSelectedTool);
      onSave();
    }
    onClose();
  };

  const handleCancel = () => {
    setTempSelectedTool(selectedTool);
    setHasChanges(false);
    onClose();
  };

  if (!visible) {
    return null;
  }

  return (
    <div className="tool-selection-sidebar-overlay">
      <div className="tool-selection-sidebar">
        <div className="tool-selection-header">
          <Typography.Title level={4}>Select Exported Tool</Typography.Title>
          <Input
            placeholder="Search tools..."
            prefix={<SearchOutlined />}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="tool-search-input"
          />
        </div>

        <div className="tool-selection-content">
          <List
            dataSource={filteredTools}
            renderItem={(tool) => (
              <List.Item
                key={tool.function_name}
                className={`tool-list-item ${
                  tempSelectedTool === tool.function_name ? "selected" : ""
                }`}
                onClick={() => handleToolSelect(tool.function_name)}
              >
                <Card
                  className="tool-card"
                  hoverable
                  size="small"
                  bordered={false}
                >
                  <div className="tool-card-content">
                    <div className="tool-info">
                      <div className="tool-header">
                        <div className="wf-tools-list">
                          {tool.icon ? (
                            <ToolIcon iconSrc={tool.icon} showBorder={true} />
                          ) : (
                            <FileTextOutlined className="tool-icon" />
                          )}
                        </div>
                        <div className="tool-details">
                          <Typography.Text strong className="tool-name">
                            {tool.name}
                          </Typography.Text>
                          <Typography.Text
                            type="secondary"
                            className="tool-description"
                          >
                            {tool.description || "No description available"}
                          </Typography.Text>
                        </div>
                      </div>
                      {tool.category && (
                        <div className="tool-category">
                          <Tag className="tool-category-tag">
                            {tool.category || "Financial Documents"}
                          </Tag>
                        </div>
                      )}
                    </div>
                  </div>
                </Card>
              </List.Item>
            )}
          />
        </div>

        <div className="tool-selection-footer">
          <Button onClick={handleCancel}>Cancel</Button>
          <Button
            type="primary"
            onClick={handleSave}
            disabled={!tempSelectedTool}
          >
            {hasChanges ? "Save Changes" : "Select Tool"}
          </Button>
        </div>
      </div>
    </div>
  );
}

ToolSelectionSidebar.propTypes = {
  visible: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  tools: PropTypes.array.isRequired,
  selectedTool: PropTypes.string,
  onToolSelect: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired,
};

export { ToolSelectionSidebar };
