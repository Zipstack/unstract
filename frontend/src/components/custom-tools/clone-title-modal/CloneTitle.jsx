import { Modal, Input, Typography, Button, Tooltip } from 'antd';
import PropTypes from 'prop-types';
import { ExclamationCircleFilled, InfoCircleOutlined } from '@ant-design/icons';
import { useCustomToolStore } from '../../../store/custom-tool-store';
import SpaceWrapper from '../../widgets/space-wrapper/SpaceWrapper';
import { useAlertStore } from '../../../store/alert-store';
import { useAxiosPrivate } from '../../../hooks/useAxiosPrivate';
import { useState } from 'react';
import { useSessionStore } from '../../../store/session-store';
import { useParams, useNavigate } from 'react-router-dom';
import { useExceptionHandler } from '../../../hooks/useExceptionHandler';
import './CloneTitle.css';
function CloneTitle({ open, setOpenCloneModal }) {
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const { id } = useParams();
  const { details, isPublicSource } = useCustomToolStore();
  const [toolName, setToolName] = useState('Copy of ' + details.tool_name);
  const handleException = useExceptionHandler();
  const navigate = useNavigate();

  const handleTitleChange = (e) => {
    const titleText = e.target.value;
    setToolName(titleText);
  };

  const handleClone = (isClone) => {
    if (isPublicSource) {
      navigate('/landing');
    } else {
      const requestOptions = {
        method: 'GET',
        url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/clone/${id}?tool_name=${toolName}`,
      };

      axiosPrivate(requestOptions)
        .then((response) => {
          const clonedTool = response?.data?.tool_id || undefined;
          setAlertDetails({
            type: 'success',
            content: 'Project cloned sucessfully',
          });
          navigate(`/${sessionDetails?.orgName}/tools/${clonedTool}`);
        })
        .catch((err) => {
          console.log(err);
          setAlertDetails(handleException(err, 'Failed to clone project'));
        });
    }
  };

  const handleClose = () => {
    setOpenCloneModal(false);
  };

  return (
    <SpaceWrapper>
      <Modal
        open={open}
        title={
          <div className="clone-title">
            <ExclamationCircleFilled
              className="clone-icons"
              style={{ fontSize: '16px', color: '#FAAD14' }}
            />
            <Typography.Text className="clone-typography-title">
              Are you sure to clone this project?
            </Typography.Text>
          </div>
        }
        onCancel={() => handleClose()}
        centered={true}
        closable={true}
        maskClosable={true}
        keyboard={true}
        footer={[
          <div className="clone-button">
            <Button onClick={() => handleClose()}>Cancel</Button>,
            <Button type="primary" onClick={() => handleClone()}>
              {isPublicSource ? 'Sign up to Clone' : 'Clone'}
            </Button>
          </div>,
        ]}
      >
        {' '}
        <div className="clone-info">
          {/* <Space direction="vertical" size="middle">
            <Typography.Text className="clone-typography">Name</Typography.Text>{' '}
          </Space> */}{' '}
          <Input
            size="default"
            value={toolName}
            onChange={handleTitleChange}
            suffix={
              <Tooltip title="Name of the clone">
                <InfoCircleOutlined style={{ color: 'rgba(0,0,0,.45)' }} />
              </Tooltip>
            }
          />{' '}
        </div>
      </Modal>
    </SpaceWrapper>
  );
}

CloneTitle.propTypes = {
  open: PropTypes.bool.isRequired,
  setOpenCloneModal: PropTypes.func.isRequired,
};

export { CloneTitle as CloneTitle };
