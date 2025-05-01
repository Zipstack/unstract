import React, { useState, useEffect } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { CopyToClipboard } from "react-copy-to-clipboard";
import { FiCopy, FiCheck } from "react-icons/fi";
import { Tooltip } from "react-tooltip";
import { useSelector } from "react-redux";
import { selectCurrentUser } from "../../../redux/auth/authSlice";
import { useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { setCurrentPrompt } from "../../../redux/prompt/promptSlice";
import { useGetPromptByIdQuery } from "../../../redux/prompt/promptApiSlice";
import { useGetPromptsByUserIdQuery } from "../../../redux/prompt/promptApiSlice";
import { useGetPromptsByUserIdAndTagQuery } from "../../../redux/prompt/promptApiSlice";
import { useGetPromptsByTagQuery } from "../../../redux/prompt/promptApiSlice";
import { useGetPromptsBySearchQuery } from "../../../redux/prompt/promptApiSlice";
import { useGetPromptsByUserIdAndSearchQuery } from "../../../redux/prompt/promptApiSlice";

const OutputForIndex = ({ output, term, tag, userId }) => {
  const [copied, setCopied] = useState(false);
  const [highlightedOutput, setHighlightedOutput] = useState(output);
  const user = useSelector(selectCurrentUser);
  const navigate = useNavigate();
  const dispatch = useDispatch();

  useEffect(() => {
    if (term && output) {
      // Use a hardcoded regex pattern or validate the term before using it
      // This prevents potential ReDoS attacks
      const safeTermPattern = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape special characters
      const regex = new RegExp(`(${safeTermPattern})`, "gi");
      
      // Apply highlighting only if the term is not potentially dangerous
      if (safeTermPattern.length > 0 && safeTermPattern.length < 100) { // Add reasonable length limit
        const parts = output.split(regex);
        const highlighted = parts.map((part, i) => {
          if (part.toLowerCase() === term.toLowerCase()) {
            return `<mark>${part}</mark>`;
          }
          return part;
        });
        setHighlightedOutput(highlighted.join(""));
      } else {
        setHighlightedOutput(output);
      }
    } else {
      setHighlightedOutput(output);
    }
  }, [output, term]);

  const handleCopy = () => {
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  };

  const handleClick = (promptId) => {
    navigate(`/prompt/${promptId}`);
  };

  return (
    <div className="relative">
      <div className="bg-gray-800 rounded-lg p-4 text-white relative">
        <div className="absolute top-2 right-2">
          <CopyToClipboard text={output} onCopy={handleCopy}>
            <button
              className="text-gray-400 hover:text-white p-1"
              data-tooltip-id="copy-tooltip"
              data-tooltip-content={copied ? "Copied!" : "Copy to clipboard"}
            >
              {copied ? <FiCheck /> : <FiCopy />}
            </button>
          </CopyToClipboard>
          <Tooltip id="copy-tooltip" />
        </div>
        <div
          className="prose prose-invert max-w-none"
          dangerouslySetInnerHTML={{ __html: highlightedOutput }}
        />
      </div>
    </div>
  );
};

export default OutputForIndex;
