import { ArrowLeftOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import PropTypes from "prop-types";

import { useSessionStore } from "../../../store/session-store.js";
import { CustomButton } from "../../widgets/custom-button/CustomButton.jsx";

import "./Header.css";

function Header({ headerText, buttonText, openAddModal, previousPage }) {
  const navigate = useNavigate();
  const { sessionDetails } = useSessionStore();
  return (
    <div className="header-layout">
      {previousPage && (
        <div>
          <Button size="small" type="text">
            <ArrowLeftOutlined
              onClick={() =>
                navigate(`/${sessionDetails.orgName}/${previousPage}`)
              }
            />
          </Button>
        </div>
      )}
      <div className="header-name">
        <Typography.Text strong>{headerText}</Typography.Text>
      </div>
      <div className="header-btns">
        <div>
          <CustomButton
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              openAddModal(true);
            }}
          >
            {buttonText}
          </CustomButton>
        </div>
      </div>
    </div>
  );
}

Header.propTypes = {
  headerText: PropTypes.string.isRequired,
  buttonText: PropTypes.string.isRequired,
  openAddModal: PropTypes.func.isRequired,
  previousPage: PropTypes.string,
};

export { Header };
