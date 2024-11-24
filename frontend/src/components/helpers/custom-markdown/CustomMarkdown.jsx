import React from "react";
import { Typography } from "antd";
import PropTypes from "prop-types";

const { Text, Link } = Typography;

const parseMarkdown = (input, renderNewLines, isSecondary, styleClassName) => {
  const elements = [];
  let index = 0;

  // Define style and type for text elements
  const textType = isSecondary ? "secondary" : undefined;
  const className = styleClassName ? styleClassName : "";

  while (index < input?.length) {
    if (input?.startsWith("**", index)) {
      // Handle bold text
      const endIndex = input.indexOf("**", index + 2);
      if (endIndex !== -1) {
        const boldText = input.substring(index + 2, endIndex);
        elements.push(
          <Text
            strong
            key={elements.length}
            type={textType}
            className={className}
          >
            {boldText}
          </Text>
        );
        index = endIndex + 2;
      } else {
        // No closing '**', treat as regular text
        elements.push(input.substring(index, index + 2));
        index += 2;
      }
    } else if (input?.[index] === "[") {
      // Handle links
      const endLinkTextIndex = input.indexOf("]", index);
      const startUrlIndex = input.indexOf("(", endLinkTextIndex);
      const endUrlIndex = input.indexOf(")", startUrlIndex);

      if (
        endLinkTextIndex !== -1 &&
        startUrlIndex === endLinkTextIndex + 1 &&
        endUrlIndex !== -1
      ) {
        const linkText = input.substring(index + 1, endLinkTextIndex);
        const url = input.substring(startUrlIndex + 1, endUrlIndex);
        elements.push(
          <Link
            href={url}
            key={elements.length}
            target="_blank"
            rel="noopener noreferrer"
            className={className}
          >
            {linkText}
          </Link>
        );
        index = endUrlIndex + 1;
      } else {
        // Not a valid link syntax, treat as regular text
        elements.push(input?.[index]);
        index += 1;
      }
    } else if (input?.[index] === "\n") {
      // Handle new lines based on the renderNewLines prop
      if (renderNewLines) {
        elements.push(<br key={elements.length} />);
      } else {
        elements.push("\n");
      }
      index += 1;
    } else {
      // Handle regular text
      let nextIndex = input.indexOf("**", index);
      const linkIndex = input.indexOf("[", index);
      const newLineIndex = input.indexOf("\n", index);

      // Find the next markdown syntax or end of string
      const indices = [nextIndex, linkIndex, newLineIndex].filter(
        (i) => i !== -1
      );
      nextIndex = indices.length > 0 ? Math.min(...indices) : -1;

      if (nextIndex === -1) {
        elements.push(input.substring(index));
        break;
      } else {
        elements.push(input.substring(index, nextIndex));
        index = nextIndex;
      }
    }
  }

  return elements;
};

const CustomMarkdown = ({
  text = "",
  renderNewLines = true,
  isSecondary = false,
  styleClassName,
}) => {
  const content = React.useMemo(
    () => parseMarkdown(text, renderNewLines, isSecondary, styleClassName),
    [text, renderNewLines, isSecondary]
  );

  const textType = isSecondary ? "secondary" : undefined;

  return (
    <Text type={textType} className={styleClassName}>
      {content}
    </Text>
  );
};

CustomMarkdown.propTypes = {
  text: PropTypes.string,
  renderNewLines: PropTypes.bool,
  isSecondary: PropTypes.bool,
  styleClassName: PropTypes.string,
};

export default CustomMarkdown;
