import { useMemo } from "react";
import { Typography } from "antd";
import PropTypes from "prop-types";

const { Text, Link, Paragraph } = Typography;

const CustomMarkdown = ({
  text = "",
  renderNewLines = true,
  isSecondary = false,
  styleClassName,
}) => {
  const textType = isSecondary ? "secondary" : undefined;

  /*
    Patterns with bounded quantifiers to prevent performance issues:
    - Triple code: ```...```
    - Inline code: `...`
    - Bold: **...**
    - Link: [text](url)
    - New line: \n
  */
  const patterns = [
    { type: "tripleCode", regex: /```\n([\s\S]*?)\n```/g },
    { type: "inlineCode", regex: /`([^`]{1,100})`/g },
    { type: "bold", regex: /\*\*([^*]{1,100})\*\*/g },
    { type: "link", regex: /\[([^\]]{1,100})\]\(([^)]{1,200})\)/g },
    { type: "newline", regex: /\n/g },
  ];

  const renderToken = (type, content, url) => {
    switch (type) {
      case "tripleCode":
        return (
          <Paragraph style={{ margin: 0 }}>
            <pre style={{ margin: 0 }}>{content}</pre>
          </Paragraph>
        );
      case "inlineCode":
        return (
          <Text code type={textType}>
            {content}
          </Text>
        );
      case "bold":
        return (
          <Text strong type={textType}>
            {content}
          </Text>
        );
      case "link":
        return (
          <Link href={url} target="_blank" rel="noopener noreferrer">
            {content}
          </Link>
        );
      case "newline":
        return renderNewLines ? <br /> : "\n";
      default:
        return content;
    }
  };

  const content = useMemo(() => {
    let elements = [text];

    // Process each pattern sequentially
    patterns.forEach(({ type, regex }) => {
      const newElements = [];
      elements.forEach((element) => {
        if (typeof element !== "string") {
          newElements.push(element);
          return;
        }

        let lastIndex = 0;
        let match;
        while ((match = regex.exec(element)) !== null) {
          const matchIndex = match.index;
          if (matchIndex > lastIndex) {
            newElements.push(element.substring(lastIndex, matchIndex));
          }
          const url = match[2]; // Relevant only for link
          newElements.push(renderToken(type, match[1], url));
          lastIndex = matchIndex + match[0].length;
        }

        if (lastIndex < element.length) {
          newElements.push(element.substring(lastIndex));
        }
      });
      elements = newElements;
    });

    return elements;
  }, [text, renderNewLines, textType]);

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
