import { Modal, Input, Typography,Button, Space} from "antd";
import PropTypes from "prop-types";
import { ExclamationCircleFilled, CloseOutlined } from "@ant-design/icons";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import SpaceWrapper from "../../widgets/space-wrapper/SpaceWrapper";
import { useAlertStore } from "../../../store/alert-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useEffect, useState } from "react";


function PromptShareLink({
  open,
  setOpenShareLink,
  setOpenShareModal,
  setOpenShareConfirmation,
}) {
  const { shareId } = useCustomToolStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const [shareURL, setShareURL] = useState(window.location.origin + "/share/"+shareId);
  useEffect(() => {
    setShareURL(window.location.origin + "/share/"+ shareId)
  }, [shareId]);

  const handleStopSharing = () => {
    setOpenShareLink(false);
    setOpenShareModal(false);
    setAlertDetails({type:"success", content:"Public sharing permissions revoked sucessfully for the project."});
  };
  const handlePublicLinkCopy = () => {
    navigator.clipboard.writeText(window.location.origin + "/share/"+ shareId);
    setAlertDetails({type:"success", content:"Public Project link copied to clipboard."});
  }
  const handleClose =() => {
    setOpenShareLink(false);
    setOpenShareModal(false);
  }

  return (
    <SpaceWrapper>
        <Modal open={open}
                title={<div class="prompt-share-title">
                <ExclamationCircleFilled className="prompt-share-icons" style={{fontSize: '16px',color:'#FAAD14'}}/>
                <Typography.Text className="prompt-share-typography-title">
                        This project is shared publicly in read-only mode.
                </Typography.Text></div>}
                onCancel={()=>handleClose()}
                centered={true}
                closable={true}
                maskClosable={true}
                keyboard={true}
                footer={[
                  <Button onClick={()=>handleStopSharing()}>
                  Stop sharing
                </Button>,
                  <Button type="primary" onClick={()=>handlePublicLinkCopy()}>
                      Copy public link
                    </Button>
                ]
                }

        >   <div class="prompt-share-info">
            <Space direction="vertical" size="middle">
            <Typography.Text className="prompt-share-typography-info">
            Prompt Studio Projects that are shared publicly will be viewable by anyone who has the generated unique link.
            </Typography.Text> </Space>
            <Input
                size="default"
                value={shareURL}
            />  </div>
        </Modal>
    </SpaceWrapper>
  );
}

PromptShareLink.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpenShareLink:PropTypes.func.isRequired,
  setOpenShareModal:PropTypes.func.isRequired,
};

export { PromptShareLink as PromptShareLink };
