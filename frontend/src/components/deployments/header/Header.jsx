import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";

import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

function Header({ type, openAddModal, enableSearch, onSearch, setSearchList }) {
  const { posthogDeploymentEventText, setPostHogCustomEvent } =
    usePostHogEvents();

  const handleOnClick = () => {
    openAddModal(false);

    try {
      setPostHogCustomEvent(posthogDeploymentEventText[type], {
        info: `Clicked on '+ ${deploymentsStaticContent[type].addBtn}' button`,
      });
    } catch (err) {
      // If an error occurs while setting custom posthog event, ignore it and continue
    }
  };

  const customButtons = () => {
    return (
      <CustomButton
        type="primary"
        icon={<PlusOutlined />}
        onClick={handleOnClick}
      >
        {deploymentsStaticContent[type].addBtn}
      </CustomButton>
    );
  };
  return (
    <ToolNavBar
      title={deploymentsStaticContent[type].title}
      CustomButtons={customButtons}
      enableSearch={enableSearch}
      onSearch={onSearch}
      setSearchList={setSearchList}
    />
  );
}

Header.propTypes = {
  type: PropTypes.string.isRequired,
  openAddModal: PropTypes.func.isRequired,
  enableSearch: PropTypes.bool,
  onSearch: PropTypes.func,
  setSearchList: PropTypes.func,
};

export { Header };
