import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";
import { deploymentsStaticContent } from "../../../helpers/GetStaticData";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { ToolNavBar } from "../../navigations/tool-nav-bar/ToolNavBar";
import { CustomButton } from "../../widgets/custom-button/CustomButton";

function Header({ type, openAddModal }) {
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
    />
  );
}

Header.propTypes = {
  type: PropTypes.string.isRequired,
  openAddModal: PropTypes.func.isRequired,
};

export { Header };
