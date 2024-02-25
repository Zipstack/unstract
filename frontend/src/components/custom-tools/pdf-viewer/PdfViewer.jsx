import { Viewer, Worker } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { handleException } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { EmptyState } from "../../widgets/empty-state/EmptyState";
import { SpinnerLoader } from "../../widgets/spinner-loader/SpinnerLoader";

function PdfViewer({ setOpenManageDocsModal }) {
  const [fileUrl, setFileUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const { selectedDoc, details } = useCustomToolStore();
  const axiosPrivate = useAxiosPrivate();

  const base64toBlob = (data) => {
    const bytes = atob(data);
    let length = bytes.length;
    const out = new Uint8Array(length);

    while (length--) {
      out[length] = bytes.charCodeAt(length);
    }

    return new Blob([out], { type: "application/pdf" });
  };

  useEffect(() => {
    if (!selectedDoc) {
      setFileUrl("");
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/fetch_contents?file_name=${selectedDoc}&tool_id=${details?.tool_id}`,
    };

    setIsLoading(true);
    axiosPrivate(requestOptions)
      .then((res) => {
        const base64String = res?.data?.data || "";
        const blob = base64toBlob(base64String);
        setFileUrl(URL.createObjectURL(blob));
      })
      .catch((err) => {
        setAlertDetails(handleException(err, "Failed to load the document"));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [selectedDoc]);

  if (isLoading) {
    return <SpinnerLoader />;
  }

  if (!selectedDoc) {
    return (
      <EmptyState
        text="Add and view your PDF document here"
        btnText="Add Document"
        handleClick={() => setOpenManageDocsModal(true)}
      />
    );
  }

  if (!fileUrl) {
    return (
      <div className="display-flex-center display-align-center">
        <Typography.Text>Failed to load the document</Typography.Text>
      </div>
    );
  }

  return (
    <div className="doc-manager-body">
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.4.120/build/pdf.worker.min.js">
        <Viewer
          fileUrl={fileUrl}
          plugins={[newPlugin, pageNavigationPluginInstance]}
        />
      </Worker>
    </div>
  );
}

PdfViewer.propTypes = {
  setOpenManageDocsModal: PropTypes.func.isRequired,
};

export { PdfViewer };
