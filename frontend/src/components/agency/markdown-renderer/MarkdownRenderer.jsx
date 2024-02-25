import PropTypes from "prop-types";
import ReactMarkdown from "markdown-to-jsx";

function MarkdownRenderer({ markdownText }) {
  return (
    <ReactMarkdown
      options={{
        overrides: {
          pre: {
            component: MyParagraph,
          },
        },
      }}
    >
      {markdownText}
    </ReactMarkdown>
  );
}

MarkdownRenderer.propTypes = {
  markdownText: PropTypes.string,
};

const MyParagraph = ({ children, ...props }) => (
  <div {...props}>{children}</div>
);

MyParagraph.propTypes = {
  children: PropTypes.any,
};

export { MarkdownRenderer };
