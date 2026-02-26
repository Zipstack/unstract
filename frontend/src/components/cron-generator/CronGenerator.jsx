import { Modal } from "antd";
import { useState } from "react";
import { Cron } from "react-js-cron";
import "react-js-cron/dist/styles.css";
import PropTypes from "prop-types";

function CronGenerator({ open, showCronGenerator, setCronValue }) {
  const [cronState, setCronState] = useState("0 * * * *");
  const handleCancel = () => {
    showCronGenerator(false);
  };

  const updateCron = () => {
    setCronValue(cronState);
    handleCancel();
  };

  return (
    <Modal
      title="Choose Cron schedule"
      open={open}
      maskClosable={false}
      closable={false}
      onCancel={handleCancel}
      onOk={updateCron}
    >
      <Cron value={cronState} setValue={setCronState} />
    </Modal>
  );
}

CronGenerator.propTypes = {
  open: PropTypes.bool.isRequired,
  showCronGenerator: PropTypes.func.isRequired,
  setCronValue: PropTypes.func.isRequired,
};

export default CronGenerator;
