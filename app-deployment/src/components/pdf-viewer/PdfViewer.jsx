import { UploadOutlined } from "@ant-design/icons";
import { Viewer, Worker } from "@react-pdf-viewer/core";
import "@react-pdf-viewer/core/lib/styles/index.css";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import "@react-pdf-viewer/page-navigation/lib/styles/index.css";
import { Button, Col, Row, Select, Upload, message } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store.js";
import { GridLayout } from "../grid-layout/GridLayout.jsx";
import { Placeholder } from "../placeholder/Placeholder.jsx";
import "./PdfViewer.css";

function PdfViewer({ selectedDoc, goToPage }) {
  const newPlugin = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();
  const { jumpToPage } = pageNavigationPluginInstance;
  const [fileList, setFileList] = useState([]);
  const [currentFile, setCurrentFile] = useState("");
  const { sessionDetails } = useSessionStore();
  const axiosPrivate = useAxiosPrivate();
  const [fileUrl, setFileUrl] = useState("");
  const props = {
    name: "file",
    action: "https://run.mocky.io/v3/435e224c-44fb-4773-9faf-380c5e6a2188",
    headers: {
      authorization: "authorization-text",
    },
    onChange(info) {
      if (info.file.status !== "uploading") {
        // file status not uploading
      }
      if (info.file.status === "done") {
        message.success(`${info.file.name} file uploaded successfully`);
      } else if (info.file.status === "error") {
        message.error(`${info.file.name} file upload failed.`);
      }
    },
  };
  const loadFile = (value) => {
    setCurrentFile(value);
    const fileApi = `/api/v1/unstract/${sessionDetails?.orgId}/get_file?app_id=${sessionDetails.appId}`;
    setFileUrl(fileApi + "&file_name=" + value);
  };
  useEffect(() => {
    const fetchData = async () => {
      try {
        const requestOptions = {
          method: "GET",
          url: `/api/v1/unstract/${sessionDetails?.orgId}/list_files/?app_id=${sessionDetails.appId}&dir_only=false`,
        };
        const res = await axiosPrivate(requestOptions);
        setFileList(res.data);
      } catch (err) {
        console.error("Error fetching data:", err);
      }
    };

    fetchData();
  }, [sessionDetails]);
  useEffect(() => {
    if (!goToPage) {
      return;
    }

    jumpToPage(goToPage - 1);
  }, [goToPage]);

  if (selectedDoc) {
    return (
      <GridLayout>
        <Placeholder
          text="Select a Document"
          subText="Please select a document from the above drop down."
        />
      </GridLayout>
    );
  }

  return (
    <GridLayout>
      <div className="pdf-viewer-layout">
        <Row gutter={16} className="pdf-selection-section">
          <Col className="gutter-row" span={16}>
            <Select
              placeholder="Select File"
              style={{ width: "100%" }}
              onChange={loadFile}
              fieldNames={{
                label: "name",
                value: "name",
              }}
              value={currentFile}
              options={fileList}
            />
          </Col>
          <Col className="gutter-row" span={6}>
            <Upload {...props}>
              <Button disabled={true} icon={<UploadOutlined />}>
                Upload
              </Button>
            </Upload>
          </Col>
          <Col className="gutter-row" span={2}>
            {/* <div>col-6</div> */}
          </Col>
        </Row>
        {fileUrl && (
          <div className="pdf-viewer">
            <Worker workerUrl="https://unpkg.com/pdfjs-dist@2.16.105/build/pdf.worker.min.js">
              <Viewer
                fileUrl={fileUrl}
                plugins={[newPlugin, pageNavigationPluginInstance]}
              />
            </Worker>
          </div>
        )}
        {!fileUrl && (
          <Placeholder
            text="Select a Document"
            subText="Please select a document from the above drop down."
          />
        )}
      </div>
    </GridLayout>
  );
}

PdfViewer.propTypes = {
  selectedDoc: PropTypes.string,
  goToPage: PropTypes.number,
};

export { PdfViewer };
