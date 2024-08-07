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
  const [isTableLoading, setIsTableLoading] = useState(false);
  const [isFormSubmitLoading, setIsFormSubmitLoading] = useState(false);
  const [editDetails, setEditDetails] = useState(null);
  const pipelineApiService = pipelineService();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (!id || !open) {
      setIsForm(false);
      setRows([]);
      return;
    }

    setIsTableLoading(true);
    pipelineApiService
      .getNotifications(type, id)
      .then((res) => {
        setRows(res?.data || []);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsTableLoading(false);
      });
  }, [id, open]);

  useEffect(() => {
    if (!isForm && editDetails) {
      setEditDetails(null);
    }
  }, [isForm]);

  const updateStatus = (record) => {
    const isActive = !record?.is_active;

    const body = {
      ...record,
      ...{
        is_active: isActive,
      },
    };

    handleUpdate(body, record?.id);
  };

  const handleSubmit = (body) => {
    setIsFormSubmitLoading(true);
    pipelineApiService
      .createNotification(body)
      .then((res) => {
        addNewRow(res?.data);
        setIsForm(false);
        setAlertDetails({
          type: "success",
          content: `Successfully created notification: ${body?.name}`,
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsFormSubmitLoading(false);
      });
  };

  const handleUpdate = (body, id) => {
    setIsFormSubmitLoading(true);
    pipelineApiService
      .updateNotification(body, id)
      .then((res) => {
        updateRow(res?.data);
        setIsForm(false);
        setAlertDetails({
          type: "success",
          content: `Successfully updated notification: ${body?.name}`,
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setIsFormSubmitLoading(false);
      });
  };

  const handleDelete = (id, name) => {
    pipelineApiService
      .deleteNotification(id)
      .then(() => {
        removeRow(id);
        setAlertDetails({
          type: "success",
          content: `Successfully delete: ${name}`,
        });
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      });
  };

  const addNewRow = (newRow) => {
    setRows((prev) => {
      const prevData = [...prev];
      prevData.push(newRow);
      return prevData;
    });
  };

  const updateRow = (updatedRow) => {
    setRows((prev) => {
      const updatedRows = [...prev];
      const index = updatedRows.findIndex(
        (item) => item?.id === updatedRow?.id
      );
      if (index !== -1) {
        updatedRows[index] = updatedRow;
      }
      return updatedRows;
    });
  };

  const removeRow = (id) => {
    setRows((prev) => {
      return prev.filter((item) => item?.id !== id);
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
        <CreateNotification
          setIsForm={setIsForm}
          addNewRow={addNewRow}
          type={type}
          id={id}
          isLoading={isFormSubmitLoading}
          handleSubmit={handleSubmit}
          handleUpdate={handleUpdate}
          editDetails={editDetails}
        />
      ) : (
        <DisplayNotifications
          setIsForm={setIsForm}
          rows={rows}
          isLoading={isTableLoading}
          updateStatus={updateStatus}
          handleDelete={handleDelete}
          setEditDetails={setEditDetails}
        />
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
