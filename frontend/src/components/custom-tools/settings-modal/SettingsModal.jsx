import {
  Code,
  Database,
  FileText,
  GitCompare,
  MessageSquare,
} from "lucide-react";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { Col, Row } from "@/components/ui/shims/antd-layout";
import { Modal } from "@/components/ui/shims/antd-overlays";
import { Menu } from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";
import { getMenuItem } from "../../../helpers/GetStaticData";
import { usePromptStudioCanEdit } from "../../../hooks/usePromptStudioCanEdit";
import { ReadOnlyNotice } from "../../widgets/read-only-notice/ReadOnlyNotice";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { CustomDataSettings } from "../custom-data-settings/CustomDataSettings";
import { CustomSynonyms } from "../custom-synonyms/CustomSynonyms";
import { ManageLlmProfiles } from "../manage-llm-profiles/ManageLlmProfiles";
import { PreAndPostAmbleModal } from "../pre-and-post-amble-modal/PreAndPostAmbleModal";

import "./SettingsModal.css";

let SummarizeManager = null;
const EvaluationManager = null;
let ChallengeManager = null;
let HighlightManager = null;
try {
  const smMod = await import(
    "../../../plugins/summarize-manager/SummarizeManager"
  );
  SummarizeManager = smMod.SummarizeManager;
  const cmMod = await import(
    "../../../plugins/challenge-manager/ChallengeManager"
  );
  ChallengeManager = cmMod.ChallengeManager;
  const hmMod = await import(
    "../../../plugins/highlight-manager/HighlightManager"
  );
  HighlightManager = hmMod.HighlightManager;
} catch {
  // Component will remain null if it is not present.
}
function SettingsModal({ open, setOpen, handleUpdateTool }) {
  // Settings hold the project's adapter credentials, so a shared user reads
  // them but cannot change them. Prompts stay editable -- that is what the
  // project was shared for.
  const canEdit = usePromptStudioCanEdit();
  const [selectedId, setSelectedId] = useState(1);
  const [menuItems, setMenuItems] = useState([]);
  const [components, setComponents] = useState([]);

  useEffect(() => {
    const items = [
      getMenuItem("LLM Profiles", 1, <Code />),
      getMenuItem("Custom Data", 9, <Database />),
      getMenuItem("Grammar", 5, <MessageSquare />),
      getMenuItem("Preamble", 6, <GitCompare />),
      getMenuItem("Postamble", 7, <GitCompare />),
    ];

    const listOfComponents = {
      1: <ManageLlmProfiles />,
      5: <CustomSynonyms />,
      6: (
        <PreAndPostAmbleModal
          type="PREAMBLE"
          handleUpdateTool={handleUpdateTool}
        />
      ),
      7: (
        <PreAndPostAmbleModal
          type="POSTAMBLE"
          handleUpdateTool={handleUpdateTool}
        />
      ),
      9: <CustomDataSettings />,
    };

    let position = 1;
    if (SummarizeManager) {
      items.splice(
        position,
        0,
        getMenuItem("SummarizedExtraction", 2, <FileText />),
      );
      listOfComponents[2] = (
        <SummarizeManager handleUpdateTool={handleUpdateTool} />
      );
      position++;
    }

    if (EvaluationManager) {
      items.splice(
        position,
        0,
        getMenuItem("Evaluation Manager", 3, <FileText />),
      );
      listOfComponents[3] = (
        <EvaluationManager handleUpdateTool={handleUpdateTool} />
      );
      position++;
    }

    if (ChallengeManager) {
      items.splice(position, 0, getMenuItem("LLMChallenge", 4, <FileText />));
      listOfComponents[4] = (
        <ChallengeManager
          handleUpdateTool={handleUpdateTool}
          type="challenge"
        />
      );
      position++;
    }
    if (HighlightManager) {
      items.push(getMenuItem("Highlighting", 8, <FileText />));
      listOfComponents[8] = (
        <HighlightManager
          handleUpdateTool={handleUpdateTool}
          type="highlight"
        />
      );
    }
    setMenuItems(items);
    setComponents(listOfComponents);
  }, []);

  const handleSelectItem = (e) => {
    const id = e.key;
    setSelectedId(id?.toString());
  };

  return (
    <Modal
      open={open}
      onCancel={() => setOpen(false)}
      maskClosable={false}
      centered
      footer={null}
      width={1200}
    >
      <SpaceWrapper>
        <div>
          <Typography.Text className="add-cus-tool-header">
            Settings
          </Typography.Text>
        </div>
        {!canEdit && (
          <ReadOnlyNotice message="Shared with you — settings are view only. Only the owner can change them." />
        )}
        <Row className="conn-modal-row" style={{ height: "800px" }}>
          <Col span={4} className="conn-modal-col conn-modal-col-left">
            <div className="conn-modal-menu conn-modal-form-pad-right">
              <Menu
                className="sidebar-menu"
                style={{ border: 0 }}
                mode="inline"
                items={menuItems}
                onClick={handleSelectItem}
                selectedKeys={[`${selectedId}`]}
              />
            </div>
          </Col>
          <Col span={20} className="conn-modal-col">
            <div
              className={`conn-modal-form-pad-left${
                canEdit ? "" : " uneditable"
              }`}
            >
              {components[selectedId]}
            </div>
          </Col>
        </Row>
      </SpaceWrapper>
    </Modal>
  );
}

SettingsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { SettingsModal };
