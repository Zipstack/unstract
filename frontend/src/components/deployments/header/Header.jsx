import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";

import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";

function Header({ type, openAddModal }) {
  const customButtons = () => {
    return (
      <CustomButton
        type="primary"
        icon={<PlusOutlined />}
        onClick={() => openAddModal(false)}
      >
        {deploymentsStaticContent[type].addBtn}
      </CustomButton>
    );
  };
  return (
    <ToolNavBar
      title={deploymentsStaticContent[type].title}
      CustomButtons={customButtons}
    />
  );
}

Header.propTypes = {
  type: PropTypes.string.isRequired,
  openAddModal: PropTypes.func.isRequired,
};

export { Header };
