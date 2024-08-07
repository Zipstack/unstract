import { Modal } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";
import { CreateNotification } from "./CreateNotification";
import { DisplayNotifications } from "./DisplayNotifications";
import { pipelineService } from "../pipeline-service";
import { useAlertStore } from "../../../store/alert-store";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";

function NotificationModal({ open, setOpen, type, id }) {
  const [isForm, setIsForm] = useState(false);
  const [rows, setRows] = useState([]);
  const pipelineApiService = pipelineService();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (!id) {
      setRows([]);
      return;
    }

    pipelineApiService
      .getNotifications(type, id)
      .then((res) => {
        setRows(res?.data || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  }, [id]);

  const addNewRow = (newRow) => {
    setRows((prev) => {
      const prevData = [...prev];
      prevData.push(newRow);
      return prevData;
    });
  };

  return (
    <Modal
      title="Setup Notifications"
      open={open}
      onCancel={() => setOpen(false)}
      centered
      footer={null}
      maskClosable={false}
    >
      {isForm ? (
        <CreateNotification setIsForm={setIsForm} addNewRow={addNewRow} />
      ) : (
        <DisplayNotifications setIsForm={setIsForm} rows={rows} />
      )}
    </Modal>
  );
}

NotificationModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpen: PropTypes.func.isRequired,
  type: PropTypes.string.isRequired,
  id: PropTypes.string,
};

export { NotificationModal };
