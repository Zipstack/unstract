import { Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { CreateNotification } from "./CreateNotification";
import { DisplayNotifications } from "./DisplayNotifications";
import { pipelineService } from "../pipeline-service";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function NotificationModal({ open, setOpen }) {
  const [isForm, setIsForm] = useState(false);
  const [rows, setRows] = useState([]);
  const pipelineApiService = pipelineService();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    pipelineApiService
      .getNotifications()
      .then((res) => {
        setRows(res?.data || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  }, []);

  useEffect(() => {
    console.log(rows);
  }, [rows]);

  return (
    <Modal
      title="Setup Notifications"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
    >
      {isForm ? (
        <CreateNotification setIsForm={setIsForm} />
      ) : (
        <DisplayNotifications setIsForm={setIsForm} />
      )}
    </Modal>
  );
}

NotificationModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
};

export { NotificationModal };
