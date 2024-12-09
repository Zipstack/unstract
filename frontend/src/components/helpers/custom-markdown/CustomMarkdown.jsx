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
  const className = styleClassName || "";

  // Single regex to capture supported markdown tokens:
  // 1. Triple code block: ```code```
  // 2. Inline code: `code`
  // 3. Bold text: **bold**
  // 4. Link: [text](url)
  // 5. New line: \n
  const tokenRegex =
    /(```((?:[^`]|`(?!``))*)```|`([^`]+)`|\*\*([^*]+)\*\*|\[([^\]]+)\]\(([^)]+)\)|\n)/g;

  const content = useMemo(() => {
    const elements = [];
    let lastIndex = 0;
    const matches = text?.matchAll(tokenRegex);

    for (const match of matches || []) {
      const matchIndex = match?.index || 0;
      // Push any preceding regular text
      if (matchIndex > lastIndex) {
        elements.push(text?.substring(lastIndex, matchIndex));
      }

      // Identify matched token
      if (match?.[2] !== undefined) {
        // Triple code block
        elements.push(
          <Paragraph
            key={elements.length}
            className={className}
            style={{ margin: 0 }}
          >
            <pre style={{ margin: 0 }}>{match?.[2]}</pre>
          </Paragraph>
        );
      } else if (match?.[3] !== undefined) {
        // Inline code
        elements.push(
          <Text
            code
            key={elements.length}
            type={textType}
            className={className}
          >
            {match?.[3]}
          </Text>
        );
      } else if (match?.[4] !== undefined) {
        // Bold text
        elements.push(
          <Text
            strong
            key={elements.length}
            type={textType}
            className={className}
          >
            {match?.[4]}
          </Text>
        );
      } else if (match?.[5] !== undefined && match?.[6] !== undefined) {
        // Link
        elements.push(
          <Link
            href={match?.[6]}
            key={elements.length}
            target="_blank"
            rel="noopener noreferrer"
            className={className}
          >
            {match?.[5]}
          </Link>
        );
      } else if (match?.[0] === "\n") {
        // New line
        elements.push(renderNewLines ? <br key={elements.length} /> : "\n");
      }

      lastIndex = matchIndex + (match?.[0]?.length || 0);
    }

    // Add remaining text after the last token
    if (lastIndex < (text?.length || 0)) {
      elements.push(text?.substring(lastIndex));
    }

    return elements;
  }, [text, renderNewLines, textType, className]);

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
