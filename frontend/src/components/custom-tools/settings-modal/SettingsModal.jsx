import { Col, Menu, Modal, Row, Typography } from "antd";
import PropTypes from "prop-types";

import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { getMenuItem } from "../../../helpers/GetStaticData";
import { useEffect, useState } from "react";
import { ManageLlmProfiles } from "../manage-llm-profiles/ManageLlmProfiles";
import { SelectLlmProfileModal } from "../select-llm-profile-modal/SelectLlmProfileModal";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { CustomSynonyms } from "../custom-synonyms/CustomSynonyms";
import { PreAndPostAmbleModal } from "../pre-and-post-amble-modal/PreAndPostAmbleModal";

function SettingsModal({
  open,
  setOpen,
  editLlmProfileId,
  setEditLlmProfileId,
  handleUpdateTool,
}) {
  const [selectedId, setSelectedId] = useState(1);
  const [llmItems, setLlmItems] = useState([]);
  const { llmProfiles } = useCustomToolStore();
  const menuItems = [
    getMenuItem("Manage LLM Profiles", 1),
    getMenuItem("Summary Manager", 2),
    getMenuItem("Manage Grammar", 3),
    getMenuItem("Preamble", 4),
    getMenuItem("Postamble", 5),
  ];

  useEffect(() => {
    getLlmProfilesDropdown();
  }, [llmProfiles]);

  const handleSelectItem = (e) => {
    const id = e.key;
    setSelectedId(id?.toString());
  };

  const getLlmProfilesDropdown = () => {
    const items = [...llmProfiles].map((item) => {
      return {
        value: item?.profile_id,
        label: item?.profile_name,
      };
    });
    setLlmItems(items);
  };

  const listOfComponents = {
    1: (
      <ManageLlmProfiles
        editLlmProfileId={editLlmProfileId}
        setEditLlmProfileId={setEditLlmProfileId}
      />
    ),
    2: (
      <SelectLlmProfileModal
        llmItems={llmItems}
        handleUpdateTool={handleUpdateTool}
      />
    ),
    3: <CustomSynonyms />,
    4: (
      <PreAndPostAmbleModal
        type="PREAMBLE"
        handleUpdateTool={handleUpdateTool}
      />
    ),
    5: (
      <PreAndPostAmbleModal
        type="POSTAMBLE"
        handleUpdateTool={handleUpdateTool}
      />
    ),
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
        <Row className="conn-modal-row" style={{ height: "800px" }}>
          <Col
            span={6}
            className="conn-modal-col conn-modal-col-left conn-modal-form-pad-right"
          >
            <div className="conn-modal-menu">
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
          <Col span={18} className="conn-modal-col conn-modal-form-pad-left">
            {listOfComponents[selectedId]}
          </Col>
        </Row>
      </SpaceWrapper>
    </Modal>
  );
}

SettingsModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  editLlmProfileId: PropTypes.string,
  setEditLlmProfileId: PropTypes.func.isRequired,
  handleUpdateTool: PropTypes.func.isRequired,
};

export { SettingsModal };
