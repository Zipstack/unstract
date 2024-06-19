import { Modal, Typography } from "antd";
import PropTypes from "prop-types";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { ExclamationCircleFilled } from "@ant-design/icons";
import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import "./PromptShareModal.css"
function PromptShareModal({
  open,
  setOpenShareConfirmation,
  setOpenShareModal,
}) {
  const { details, updateCustomTool } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();
  const axiosPrivate = useAxiosPrivate();

  const handleCancel = () => {
    setOpenShareModal(false);
    setOpenShareConfirmation(false)
  }
  const handlePublicShare = () => {
    const requestOptions = {
      method: "POST",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/share-manager/?id=${details?.tool_id}`,
      headers: {
        "X-CSRFToken": sessionDetails?.csrfToken,
        "Content-Type": "application/json",
      },
      data: {
        share_type: "PROMPT_STUDIO",
      },
    };
    axiosPrivate(requestOptions)
      .then((res) => {
        let data = res?.data;
        const updatedDetails = { shareId:data?.share_id };
        updateCustomTool(updatedDetails);
        setAlertDetails({type:"success", content:"Project shared sucessfully."});
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to generate share link"));
      });
  };

  return (
        <Modal
                open={open}
                title={
                <div class="prompt-share-title">
                    <ExclamationCircleFilled className="prompt-share-icons" style={{fontSize: '16px',color:'#FAAD14'}}/>
                    <Typography.Text className="prompt-share-typography-title">
                    Share this project publicly in read-only mode?
                    </Typography.Text>
                </div>}
                okText="Yes, enable sharing."
                cancelText="Cancel"
                onCancel={()=>{handleCancel()}}
                onOk={()=>handlePublicShare()}
                centered
                maskClosable={false}
                closable={false}
        >
           <div class="prompt-share-info">
          <Typography.Text className="prompt-share-typography-info">
          Prompt Studio Projects that are shared publicly will be viewable by anyone who has the generated unique link.
          </Typography.Text> </div>
        </Modal>
  );
}

PromptShareModal.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpenShareConfirmation: PropTypes.func.isRequired,
  setOpenShareModal: PropTypes.func.isRequired,
};

export { PromptShareModal };
