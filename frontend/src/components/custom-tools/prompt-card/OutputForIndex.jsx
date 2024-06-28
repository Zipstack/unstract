import PropTypes from "prop-types";
import { Modal } from "antd";
import "./PromptCard.css";
import { uniqueId } from "lodash";

function OutputForIndex({ chuckData, setIsIndexOpen, isIndexOpen }) {
  const handleClose = () => {
    setIsIndexOpen(false);
  };

  const lines = chuckData?.split("\\n"); // Split text into lines and remove any empty lines

  const renderContent = (chuck) => {
    return !chuck ? (
      <p>No chucks founds</p>
    ) : (
      <>
        {chuck?.map((line) => (
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
      <div className="index-output-tab">{renderContent(lines)}</div>
    </Modal>
  );
}

OutputForIndex.propTypes = {
  chuckData: PropTypes.string,
  isIndexOpen: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
};

export { OutputForIndex };
