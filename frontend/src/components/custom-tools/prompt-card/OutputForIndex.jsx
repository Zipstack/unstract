import PropTypes from "prop-types";
import { useState, useEffect, useRef, useCallback } from "react";
import { Modal, Input, Button, Typography } from "antd";
import "./PromptCard.css";
import { uniqueId } from "lodash";
import debounce from "lodash/debounce";
import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons";

import { TextViewerPre } from "../text-viewer-pre/TextViewerPre";

function OutputForIndex({ chunkData, setIsIndexOpen, isIndexOpen }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [highlightedChunks, setHighlightedChunks] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [chunks, setChunks] = useState([]);
  const activeRef = useRef(null);

  useEffect(() => {
    setChunks(chunkData || []);
  }, [chunkData]);

  // Debounced search handler
  const handleSearch = useCallback(
    debounce((term) => {
      if (!term) {
        setHighlightedChunks([]);
        return;
      }
      const allResults = [];
      chunks?.forEach((chunk, chunkIndex) => {
        const lines = chunk?.split("\\n");
        lines.forEach((line, lineIndex) => {
          const regex = new RegExp(`(${term})`, "gi");
          let match;
          while ((match = regex.exec(line)) !== null) {
            allResults.push({
              chunkIndex,
              lineIndex,
              startIndex: match?.index,
              matchLength: match[0]?.length,
            });
          }
        });
      });
      setHighlightedChunks(allResults);
      setCurrentIndex(0);
    }, 300), // Debounce delay in milliseconds
    [chunks]
  );

  useEffect(() => {
    handleSearch(searchTerm);
  }, [searchTerm]);

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [currentIndex]);

  const handleClose = () => {
    setIsIndexOpen(false);
    setSearchTerm("");
    setHighlightedChunks([]);
    setCurrentIndex(0);
  };

  const handleSearchChange = (e) => {
    setSearchTerm(e.target.value);
  };

  const handleNext = () => {
    setCurrentIndex((prev) => (prev + 1) % highlightedChunks?.length);
  };

  const handlePrev = () => {
    setCurrentIndex((prev) =>
      prev === 0 ? highlightedChunks?.length - 1 : prev - 1
    );
  };

  const renderHighlightedLine = (line, lineIndex, chunkIndex) => {
    if (!searchTerm) return line;

    const matchesInLine = highlightedChunks.filter(
      (chunk) =>
        chunk.lineIndex === lineIndex && chunk.chunkIndex === chunkIndex
    );

    if (!matchesInLine?.length) return line;

    const parts = [];
    let lastIndex = 0;

    matchesInLine.forEach((match, idx) => {
      if (lastIndex < match.startIndex) {
        parts.push(line.substring(lastIndex, match.startIndex));
      }

      const isActive =
        currentIndex ===
        highlightedChunks.findIndex(
          (h) =>
            h.chunkIndex === chunkIndex &&
            h.lineIndex === lineIndex &&
            h.startIndex === match.startIndex
        );

      parts.push(
        <span
          key={uniqueId()}
          className={`chunk-highlight ${
            isActive ? "active-chunk-highlight" : ""
          }`}
          ref={isActive ? activeRef : null}
        >
          {line.substring(
            match.startIndex,
            match.startIndex + match.matchLength
          )}
        </span>
      );

      lastIndex = match.startIndex + match.matchLength;
    });

    if (lastIndex < line.length) {
      parts.push(line.substring(lastIndex));
    }

    return parts;
  };

  return (
    <Modal
      title="Index Data"
      open={isIndexOpen}
      onCancel={handleClose}
      className="index-output-modal"
      centered
      footer={null}
      width={1000}
    >
      <div className="chunk-search-container">
        <Input
          placeholder="Search..."
          value={searchTerm}
          onChange={handleSearchChange}
          className="chunk-search-input"
        />
        <div className="search-control-container">
          <Button
            size="small"
            onClick={handlePrev}
            disabled={highlightedChunks.length === 0}
          >
            <ArrowUpOutlined />
          </Button>
          <span className="page-count-container">
            {highlightedChunks.length > 0 ? currentIndex + 1 : 0}/{" "}
            {highlightedChunks.length}
          </span>
          <Button
            size="small"
            onClick={handleNext}
            disabled={highlightedChunks.length === 0}
          >
            <ArrowDownOutlined />
          </Button>
        </div>
      </div>
      <div className="index-output-tab">
        {chunks?.map((chunk, chunkIndex) => (
          <div key={uniqueId()} className="chunk-container">
            <Typography.Text strong>Chunk {chunkIndex + 1}</Typography.Text>
            <TextViewerPre
              text={
                <>
                  {chunk?.split("\\n")?.map((line, lineIndex) => (
                    <div key={uniqueId()}>
                      {renderHighlightedLine(line, lineIndex, chunkIndex)}
                      <br />
                    </div>
                  ))}
                </>
              }
            />
          </div>
        ))}
      </div>
    </Modal>
  );
}

OutputForIndex.propTypes = {
  chunkData: PropTypes.string,
  isIndexOpen: PropTypes.bool.isRequired,
  setIsIndexOpen: PropTypes.func.isRequired,
};

export { OutputForIndex };
