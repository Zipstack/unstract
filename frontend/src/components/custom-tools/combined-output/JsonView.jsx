import PropTypes from "prop-types";
import Prism from "prismjs";
import { useEffect } from "react";

function JsonView({ combinedOutput }) {
  useEffect(() => {
    Prism.highlightAll();
  }, [combinedOutput]);

  return (
    <div className="combined-op-layout">
      <div className="combined-op-header">
        <div className="combined-op-segment"></div>
      </div>
      <div className="combined-op-divider" />
      <div className="combined-op-body code-snippet">
        {combinedOutput && (
          <pre className="line-numbers width-100">
            <code className="language-javascript width-100">
              {JSON.stringify(combinedOutput, null, 2)}
            </code>
          </pre>
        )}
      </div>
      <div className="gap" />
    </div>
  );
}

JsonView.propTypes = {
  combinedOutput: PropTypes.object.isRequired,
};

export { JsonView };
