import { Button, Drawer, Menu, Space, Typography } from "antd";
import {
  ArrowLeftOutlined,
  FilePdfOutlined,
  FilterOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import PropTypes from "prop-types";
import { useSessionStore } from "../../../store/session-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useMemo, useCallback, useState } from "react";

let HeaderPublic;
try {
  HeaderPublic =
    require("../../../plugins/prompt-studio-public-share/header-public/HeaderPublic.jsx").HeaderPublic;
} catch (err) {
  // Do nothing if plugins are not loaded.
}

const PAGINATION_ACTIONS = {
  PREV: "PREV",
  NEXT: "NEXT",
};

function OutputAnalyzerHeader({
  docs,
  currentDocIndex,
  setCurrentDocIndex,
  selectedPrompts,
  openFilterDrawer,
}) {
  const { sessionDetails } = useSessionStore();
  const { id } = useParams();
  const navigate = useNavigate();
  const { isPublicSource } = useCustomToolStore();
  const [openDocListDrawer, setOpenDocListDrawer] = useState(false);

  const docsLength = docs?.length || 0;

  const selectedPromptFields = useMemo(() => {
    return Object.values(selectedPrompts).filter(Boolean).length;
  }, [selectedPrompts]);

  const menuItems = useMemo(
    () =>
      docs.map((doc, docIndex) => ({
        key: docIndex.toString(),
        label: doc?.document_name,
      })),
    [docs]
  );

  const handleNavigate = useCallback(() => {
    const path = isPublicSource
      ? `/promptStudio/share/${id}`
      : `/${sessionDetails?.orgName}/tools/${id}`;
    navigate(path);
  }, []);

  const handlePagination = useCallback((action) => {
    setCurrentDocIndex((prevIndex) => {
      let delta = 0;

      if (action === PAGINATION_ACTIONS.PREV) {
        delta = -1;
      } else if (action === PAGINATION_ACTIONS.NEXT) {
        delta = 1;
      }

      return Math.max(0, Math.min(prevIndex + delta, docsLength - 1));
    });
  }, []);

  const handleSelectionOfDoc = useCallback((selectedDoc) => {
    setCurrentDocIndex(parseInt(selectedDoc.key, 10));
  }, []);

  return (
    <div>
      {isPublicSource && HeaderPublic && <HeaderPublic />}
      <div className="output-analyzer-header">
        <div>
          <Space>
            <Button size="small" type="text" onClick={handleNavigate}>
              <ArrowLeftOutlined />
            </Button>
            <Typography.Text className="font-size-16" strong>
              Output Analyzer
            </Typography.Text>
          </Space>
        </div>
        <div>
          <Space>
            <Button
              type="text"
              icon={<FilterOutlined />}
              onClick={openFilterDrawer}
            >{`${selectedPromptFields} of ${
              Object.keys(selectedPrompts).length
            } fields selected`}</Button>
            <Button
              type="primary"
              icon={<FilePdfOutlined />}
              onClick={() => setOpenDocListDrawer(true)}
            />
            <div>
              <Button
                type="text"
                icon={<LeftOutlined />}
                onClick={() => handlePagination(PAGINATION_ACTIONS.PREV)}
                disabled={currentDocIndex === 0}
              />
              <Button
                type="text"
                icon={<RightOutlined />}
                onClick={() => handlePagination(PAGINATION_ACTIONS.NEXT)}
                disabled={currentDocIndex === docsLength - 1}
              />
            </div>
          </Space>
        </div>
      </div>
      <Drawer
        title="Document List"
        open={openDocListDrawer}
        onClose={() => setOpenDocListDrawer(false)}
      >
        <Menu
          selectedKeys={[currentDocIndex.toString()]}
          items={menuItems}
          onSelect={handleSelectionOfDoc}
        />
      </Drawer>
    </div>
  );
}

OutputAnalyzerHeader.propTypes = {
  docs: PropTypes.array.isRequired,
  currentDocIndex: PropTypes.number.isRequired,
  setCurrentDocIndex: PropTypes.func.isRequired,
  selectedPrompts: PropTypes.object.isRequired,
  openFilterDrawer: PropTypes.func.isRequired,
};

export { OutputAnalyzerHeader };
