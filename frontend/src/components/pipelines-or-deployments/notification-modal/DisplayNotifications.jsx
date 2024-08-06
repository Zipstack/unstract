import PropTypes from "prop-types";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { Button, Table } from "antd";
import { PlusOutlined } from "@ant-design/icons";

function DisplayNotifications({ setIsForm }) {
  return (
    <SpaceWrapper>
      <div className="display-flex-right">
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => setIsForm(true)}
        >
          Create Notification
        </Button>
      </div>
      <Table />
    </SpaceWrapper>
  );
}

DisplayNotifications.propTypes = {
  setIsForm: PropTypes.func.isRequired,
};

export { DisplayNotifications };
