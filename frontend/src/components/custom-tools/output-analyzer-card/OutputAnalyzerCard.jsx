import { Col, Divider, Flex, Row, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { base64toBlob } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CombinedOutput } from "../combined-output/CombinedOutput";
import { DocumentViewer } from "../document-viewer/DocumentViewer";
import { PdfViewer } from "../pdf-viewer/PdfViewer";

function OutputAnalyzerCard({ doc, totalFields }) {
  const [fileUrl, setFileUrl] = useState("");
  const [isDocLoading, setIsDocLoading] = useState(false);
  const [filledFields, setFilledFields] = useState(0);
  const { details } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();

  useEffect(() => {
    if (!doc) {
      setFileUrl("");
      return;
    }

    const requestOptions = {
      method: "GET",
      url: `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/${details?.tool_id}?document_id=${doc?.document_id}`,
    };

    setIsDocLoading(true);
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
        setIsDocLoading(false);
      });
  }, [doc]);

  return (
    <div className="output-analyzer-body2">
      <div className="output-analyzer-card-head">
        <Space>
          <Typography.Text strong>{doc?.document_name}</Typography.Text>
        </Space>
        <Flex>
          <div>
            <Typography.Text>
              Total top-level fields: <strong>{totalFields}</strong>
            </Typography.Text>
            <Divider type="vertical" />
          </div>
          <div>
            <Typography.Text>
              Fill rate: <strong>NA</strong>
            </Typography.Text>
            <Divider type="vertical" />
          </div>
          <div>
            <Typography.Text>
              Filled fields: <strong>{filledFields}</strong>
            </Typography.Text>
            <Divider type="vertical" />
          </div>
          <div>
            <Typography.Text>
              Unfilled fields: <strong>{totalFields - filledFields}</strong>
            </Typography.Text>
          </div>
        </Flex>
      </div>
      <div className="output-analyzer-main">
        <Row className="height-100">
          <Col span={12} className="height-100">
            <div className="output-analyzer-left-box">
              <DocumentViewer
                doc={doc}
                isLoading={isDocLoading}
                isContentAvailable={fileUrl?.length > 0}
              >
                <PdfViewer fileUrl={fileUrl} />
              </DocumentViewer>
            </div>
          </Col>
          <Col span={12} className="height-100">
            <div className="output-analyzer-right-box">
              <CombinedOutput
                docId={doc?.document_id}
                setFilledFields={setFilledFields}
              />
            </div>
          </Col>
        </Row>
      </div>
    </div>
  );
}

OutputAnalyzerCard.propTypes = {
  doc: PropTypes.object.isRequired,
  totalFields: PropTypes.number.isRequired,
};

export { OutputAnalyzerCard };
