import { useEffect, useState } from "react";
import mammoth from "mammoth";
import PropTypes from "prop-types";
import { Select, Button, Row, Col } from "antd";
import { ZoomInOutlined, ZoomOutOutlined } from "@ant-design/icons";

const { Option } = Select;

const DocxViewer = ({ fileUrl }) => {
  const [content, setContent] = useState("");
  const [zoom, setZoom] = useState(100);

  useEffect(() => {
    const fetchContent = async () => {
      const response = await fetch(fileUrl);
      const arrayBuffer = await response.arrayBuffer();
      mammoth
        .convertToHtml({ arrayBuffer: arrayBuffer })
        .then((result) => {
          setContent(result.value); // The generated HTML
        })
        .catch((err) => {
          console.error("Error converting DOCX:", err);
          setContent("Error loading document.");
        });
    };

    fetchContent();
  }, [fileUrl]);

  const handleZoomChange = (value) => {
    setZoom(value);
  };

  const handleZoomIn = () => {
    setZoom((prevZoom) => Math.min(prevZoom + 10, 200));
  };

  const handleZoomOut = () => {
    setZoom((prevZoom) => Math.max(prevZoom - 10, 70));
  };

  return (
    <div style={{ maxHeight: "100vh", overflowY: "auto", padding: "10px" }}>
      <Row justify="center" align="middle" style={{ marginBottom: "10px" }}>
        <Col>
          <Button icon={<ZoomOutOutlined />} onClick={handleZoomOut} />
        </Col>
        <Col>
          <Select
            value={zoom + "%"}
            style={{ width: 100, margin: "0 10px" }}
            onChange={handleZoomChange}
          >
            <Option value={70}>70%</Option>
            <Option value={100}>100%</Option>
            <Option value={125}>125%</Option>
            <Option value={150}>150%</Option>
            <Option value={200}>200%</Option>
          </Select>
        </Col>
        <Col>
          <Button icon={<ZoomInOutlined />} onClick={handleZoomIn} />
        </Col>
      </Row>
      <div
        style={{
          transform: `scale(${zoom / 100})`,
          transformOrigin: "top left",
          height: "100%",
          overflowY: "auto",
        }}
        dangerouslySetInnerHTML={{ __html: content }}
      />
    </div>
  );
};

export { DocxViewer };

DocxViewer.propTypes = {
  fileUrl: PropTypes.string.isRequired,
};
