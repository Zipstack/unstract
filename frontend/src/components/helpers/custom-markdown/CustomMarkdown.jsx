import React from "react";
import { Typography } from "antd";
import PropTypes from "prop-types";

const { Text, Link } = Typography;

const CustomMarkdown = ({
  text = "",
  renderNewLines = true,
  isSecondary = false,
  styleClassName,
}) => {
  const textType = isSecondary ? "secondary" : undefined;
  const className = styleClassName || "";

  const parseMarkdown = React.useCallback(() => {
    const elements = [];
    let index = 0;
    const input = text;

    // Helper functions for parsing different markdown elements
    const parseCodeBlock = () => {
      const endIndex = input.indexOf("```", index + 3);
      if (endIndex !== -1) {
        const codeText = input.substring(index + 3, endIndex);
        elements.push(
          <Text
            code
            key={elements.length}
            type={textType}
            className={className}
            style={{ display: "block", whiteSpace: "pre-wrap" }}
          >
            {codeText}
          </Text>
        );
        index = endIndex + 3;
        return true;
      }
      return false;
    };

    const parseInlineCode = () => {
      const endIndex = input.indexOf("`", index + 1);
      if (endIndex !== -1) {
        const codeText = input.substring(index + 1, endIndex);
        elements.push(
          <Text
            code
            key={elements.length}
            type={textType}
            className={className}
          >
            {codeText}
          </Text>
        );
        index = endIndex + 1;
        return true;
      }
      return false;
    };

    const parseBoldText = () => {
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
        return true;
      }
      return false;
    };

    const parseLink = () => {
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
        return true;
      }
      return false;
    };

    while (index < input.length) {
      const char = input[index];

      if (input.startsWith("```", index)) {
        if (parseCodeBlock()) continue;
      } else if (input.startsWith("`", index)) {
        if (parseInlineCode()) continue;
      } else if (input.startsWith("**", index)) {
        if (parseBoldText()) continue;
      } else if (char === "[") {
        if (parseLink()) continue;
      } else if (char === "\n") {
        // Handle new lines
        if (renderNewLines) {
          elements.push(<br key={elements.length} />);
        } else {
          elements.push("\n");
        }
        index += 1;
        continue;
      }

      // Handle regular text
      let nextIndex = input.length;
      const nextSpecialIndices = [
        input.indexOf("```", index),
        input.indexOf("`", index),
        input.indexOf("**", index),
        input.indexOf("[", index),
        input.indexOf("\n", index),
      ].filter((i) => i !== -1);

      if (nextSpecialIndices.length > 0) {
        nextIndex = Math.min(...nextSpecialIndices);
      }

      const textSegment = input.substring(index, nextIndex);
      elements.push(textSegment);
      index = nextIndex;
    }

    return elements;
  }, [text, renderNewLines, textType, className]);

  const content = React.useMemo(() => parseMarkdown(), [parseMarkdown]);

  return (
    <Text type={textType} className={className}>
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
