import { Typography } from "antd";
import PropTypes from "prop-types";

import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function DocumentViewer({
  children,
  doc,
  isLoading,
  isContentAvailable,
  setOpenManageDocsModal,
  errMsg,
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
      <div className="height-100 display-flex-center display-flex-align-center">
        <Typography.Text>
          {errMsg || "Loading onboarding document"}
        </Typography.Text>
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
  errMsg: PropTypes.string,
};

export { DocumentViewer };
