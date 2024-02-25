import { Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import PropTypes from "prop-types";

import { CustomButton } from "../../widgets/custom-button/CustomButton";
import { deploymentsStaticContent } from "../../../helpers/GetStaticData";

function Header({ type, openAddModal }) {
  return (
    <div className="layout-header">
      <div>
        <Typography.Text strong className="title">
          {deploymentsStaticContent[type].title}
        </Typography.Text>
      </div>
      <div>
        <CustomButton
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => openAddModal(false)}
        >
          {deploymentsStaticContent[type].addBtn}
        </CustomButton>
      </div>
    </div>
  );
}

Header.propTypes = {
  type: PropTypes.string.isRequired,
  openAddModal: PropTypes.func.isRequired,
};

export { Header };
