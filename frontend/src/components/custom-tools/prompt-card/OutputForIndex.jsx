import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import { Modal, Tabs } from "antd";
import { useSessionStore } from "../../../store/session-store";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import TabPane from "antd/es/tabs/TabPane";
import { TextViewerPre } from "../text-viewer-pre/TextViewerPre";
import "./PromptCard.css";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function OutputForIndex({ llmProfileId, isIndexOpen, setIsIndexOpen }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();

  const fetchData = () => {
    setLoading(true);
    axiosPrivate
      .get(
        `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/indexed-result/?profile_manager=${llmProfileId}`
      )
      .then((response) => {
        setData(response.data);
      })
      .catch((err) => {
        setAlertDetails(handleException(err));
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    if (isIndexOpen) {
      fetchData();
    }
  }, [isIndexOpen]);

  const handleClose = () => {
    setIsIndexOpen(false);
  };

  const renderContent = (content) => {
    if (Array.isArray(content)) {
      return content.length === 0 ? (
        <p>File not indexed</p>
      ) : (
        <>
          {content.map((text, index) => (
            <TextViewerPre text={text} key={index} />
          ))}
        </>
      );
    }
    return <p>Invalid data format</p>;
  };

  return (
    <>
      <Modal
        title="Document Data"
        open={isIndexOpen}
        onCancel={handleClose}
        width={"90%"}
        className="index-output-modal"
        centered
        footer={<></>}
      >
        {loading ? (
          <div>
            <SpinnerLoader />
          </div>
        ) : (
          <Tabs>
            {data &&
              Object.keys(data).map((key) => (
                <TabPane className="index-output-tab" tab={key} key={key}>
                  {renderContent(data[key])}
                </TabPane>
              ))}
          </Tabs>
        )}
      </Modal>
    </>
  );
}

OutputForIndex.propTypes = {
  llmProfileId: PropTypes.text,
  isIndexOpen: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
};

export { OutputForIndex };
