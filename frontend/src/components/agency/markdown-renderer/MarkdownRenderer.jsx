import PropTypes from "prop-types";
import { memo, useMemo } from "react";
import { Remarkable } from "remarkable";

const md = new Remarkable();

const MarkdownRenderer = memo(({ markdownText }) => {
  const htmlContent = useMemo(() => {
    if (!markdownText) return "";
    return md.render(markdownText);
  }, [markdownText]);

  return <div dangerouslySetInnerHTML={{ __html: htmlContent }} />;
});

MarkdownRenderer.displayName = "MarkdownRenderer";

MarkdownRenderer.propTypes = {
  markdownText: PropTypes.string,
};

export { MarkdownRenderer };
