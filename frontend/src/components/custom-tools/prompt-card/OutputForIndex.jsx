import PropTypes from "prop-types";
import { Modal } from "antd";
import "./PromptCard.css";
import { uniqueId } from "lodash";

import { TextViewerPre } from "../text-viewer-pre/TextViewerPre";

function OutputForIndex({ chunkData, setIsIndexOpen, isIndexOpen }) {
  const handleClose = () => {
    setIsIndexOpen(false);
  };

  const lines = chunkData?.split("\\n"); // Split text into lines and remove any empty lines

  const renderContent = (chunk) => {
    if (!chunk) {
      return <p>No chunks founds</p>;
    }
    return (
      <>
        {chunk?.map((line) => (
          <div key={uniqueId()}>
            {line}
            <br />
          </div>
        ))}
      </>
    );
  };

  return (
    <Modal
      title="Index Data"
      open={isIndexOpen}
      onCancel={handleClose}
      className="index-output-modal"
      centered
      footer={null}
      width={1000}
    >
      <div className="index-output-tab">
        <TextViewerPre text={renderContent(lines)} />
      </div>
    </Modal>
  );
}

OutputForIndex.propTypes = {
  chunkData: PropTypes.string,
  isIndexOpen: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
};

export { OutputForIndex };
