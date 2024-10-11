import { Col, Divider, Flex, Row, Space, Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState, useMemo } from "react";
import { useParams } from "react-router-dom";

import { base64toBlob } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler";
import { useAlertStore } from "../../../store/alert-store";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useSessionStore } from "../../../store/session-store";
import { CombinedOutput } from "../combined-output/CombinedOutput";
import { DocumentViewer } from "../document-viewer/DocumentViewer";
import { PdfViewer } from "../pdf-viewer/PdfViewer";

let publicDocumentApi;
try {
  publicDocumentApi =
    require("../../../plugins/prompt-studio-public-share/helpers/PublicShareAPIs").publicDocumentApi;
} catch {
  // The component will remain null if it is not available
}

function OutputAnalyzerCard({ doc, selectedPrompts, totalFields }) {
  const [fileUrl, setFileUrl] = useState("");
  const [isDocLoading, setIsDocLoading] = useState(false);
  const [filledFields, setFilledFields] = useState(0);

  const { details, isPublicSource } = useCustomToolStore();
  const { sessionDetails } = useSessionStore();
  const { setAlertDetails } = useAlertStore();
  const axiosPrivate = useAxiosPrivate();
  const handleException = useExceptionHandler();
  const { id } = useParams();

  // Memoize the file URL endpoint to prevent unnecessary recalculations
  const fileUrlEndpoint = useMemo(() => {
    if (!doc) return null;

    if (isPublicSource) {
      return publicDocumentApi?.(id, doc.document_id, null);
    } else {
      return `/api/v1/unstract/${sessionDetails?.orgId}/prompt-studio/file/${details?.tool_id}?document_id=${doc?.document_id}`;
    }
  }, [doc]);

  // Fetch the document file when the endpoint changes
  useEffect(() => {
    if (!fileUrlEndpoint) {
      setFileUrl("");
      return;
    }

    const fetchFile = async () => {
      setIsDocLoading(true);
      try {
        const res = await axiosPrivate.get(fileUrlEndpoint);
        const base64String = res?.data?.data || "";
        const blob = base64toBlob(base64String);
        setFileUrl(URL.createObjectURL(blob));
      } catch (err) {
        setAlertDetails(handleException(err, "Failed to load the document"));
      } finally {
        setIsDocLoading(false);
      }
    };

    fetchFile();
  }, [fileUrlEndpoint]);

  // Calculate fill rate
  const fillRate = useMemo(() => {
    if (totalFields === 0) return "0";
    return ((filledFields / totalFields) * 100).toFixed(2);
  }, [filledFields, totalFields]);

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
              Fill rate: <strong>{`${fillRate}%`}</strong>
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
              <CombinedOutput
                docId={doc?.document_id}
                selectedPrompts={selectedPrompts}
                setFilledFields={setFilledFields}
              />
            </div>
          </Col>
          <Col span={12} className="height-100">
            <div className="output-analyzer-right-box">
              <DocumentViewer
                doc={doc}
                isLoading={isDocLoading}
                isContentAvailable={Boolean(fileUrl)}
              >
                <PdfViewer fileUrl={fileUrl} />
              </DocumentViewer>
            </div>
          </Col>
        </Row>
      </div>
    </div>
  );
}

OutputAnalyzerCard.propTypes = {
  doc: PropTypes.object.isRequired,
  selectedPrompts: PropTypes.object.isRequired,
  totalFields: PropTypes.number.isRequired,
};

export { OutputAnalyzerCard };
