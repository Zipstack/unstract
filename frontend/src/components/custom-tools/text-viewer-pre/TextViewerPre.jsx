import PropTypes from "prop-types";
import escapeHTML from "escape-html";

function TextViewerPre({ text }) {
  return (
    <div className="text-viewer-layout">
      <pre style={{ fontSize: "12px" }}>{escapeHTML(text)}</pre>
    </div>
  );
}

TextViewerPre.propTypes = {
  text: PropTypes.string,
};

export { TextViewerPre };
