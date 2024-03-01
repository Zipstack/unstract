import PropTypes from "prop-types";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { Typography } from "antd";

function DocumentViewer({
  children,
  doc,
  isLoading,
  isContentAvailable,
  setOpenManageDocsModal,
}) {
  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (!doc) {
    return (
      <EmptyState
        text="Add and view your PDF document here"
        btnText="Add Document"
        handleClick={() => setOpenManageDocsModal(true)}
      />
    );
  }

  if (!isContentAvailable) {
    return (
      <div className="display-flex-center display-align-center">
        <Typography.Text>Failed to load the document</Typography.Text>
      </div>
    );
  }

  return <>{children}</>;
}

DocumentViewer.propTypes = {
  children: PropTypes.any.isRequired,
  doc: PropTypes.string,
  isLoading: PropTypes.bool.isRequired,
  isContentAvailable: PropTypes.bool.isRequired,
  setOpenManageDocsModal: PropTypes.func,
};

export { DocumentViewer };
