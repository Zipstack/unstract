import Prism from "prismjs";
import "prismjs/themes/prism.css";
import PropTypes from "prop-types";
import { useEffect } from "react";

import "./CodeSnippet.css";

const CodeSnippet = ({ code }) => {
  useEffect(() => {
    Prism.highlightAll();
  }, [code]);
  return (
    <pre className="codeSnippet">
      <code className="language-javascript">{code}</code>
    </pre>
  );
};

CodeSnippet.propTypes = {
  code: PropTypes.string.isRequired,
};

export default CodeSnippet;
