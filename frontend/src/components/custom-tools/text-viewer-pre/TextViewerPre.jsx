import PropTypes from "prop-types";

function TextViewerPre({ text }) {
  return (
    <div className="text-viewer-layout">
      <pre style={{ fontSize: "12px" }}>{text}</pre>
    </div>
  );
}

TextViewerPre.propTypes = {
  text: PropTypes.string,
};

export { TextViewerPre };
