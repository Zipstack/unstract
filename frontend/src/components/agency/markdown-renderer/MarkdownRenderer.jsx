import PropTypes from "prop-types";
import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MarkdownRenderer = memo(({ markdownText }) => {
  if (!markdownText) return null;

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdownText}</ReactMarkdown>
  );
});

MarkdownRenderer.displayName = "MarkdownRenderer";

MarkdownRenderer.propTypes = {
  markdownText: PropTypes.string,
};

export { MarkdownRenderer };
