import { useEffect, useState, useMemo, useCallback } from "react";
import { Drawer } from "antd";

import { OutputAnalyzerHeader } from "./OutputAnalyzerHeader";
import "./OutputAnalyzer.css";
import { OutputAnalyzerCard } from "./OutputAnalyzerCard";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { promptType } from "../../../helpers/GetStaticData";
import { FilterPromptFields } from "./FilterPromptFields";

function OutputAnalyzer() {
  const [currentDocIndex, setCurrentDocIndex] = useState(-1);
  const { listOfDocs, details, isPublicSource, selectedDoc } =
    useCustomToolStore();
  const [selectedPrompts, setSelectedPrompts] = useState({});
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);

  useEffect(() => {
    const allPrompts = details?.prompts || [];
    const promptFields = allPrompts.filter(
      (item) => item?.prompt_type === promptType.prompt
    );

    const initialSelectedPrompts = promptFields.reduce((acc, item) => {
      acc[item?.prompt_key] = true;
      return acc;
    }, {});

    setSelectedPrompts(initialSelectedPrompts);

    const selectedDocIndex =
      listOfDocs.findIndex(
        (doc) => doc?.document_id === selectedDoc?.document_id
      ) || 0;
    setCurrentDocIndex(selectedDocIndex);
  }, []);

  const totalFields = useMemo(() => {
    return Object.values(selectedPrompts).filter(Boolean).length;
  }, [selectedPrompts]);

  const openFilterDrawer = useCallback(() => {
    setIsFilterDrawerOpen(true);
  }, []);

  const closeFilterDrawer = useCallback(() => {
    setIsFilterDrawerOpen(false);
  }, []);

  const currentDoc = useMemo(() => {
    if (currentDocIndex === -1) return null;
    return listOfDocs[currentDocIndex];
  }, [listOfDocs, currentDocIndex]);

  return (
    <div className="output-analyzer-layout">
      <div>
        <OutputAnalyzerHeader
          docs={listOfDocs}
          currentDocIndex={currentDocIndex}
          setCurrentDocIndex={setCurrentDocIndex}
          selectedPrompts={selectedPrompts}
          openFilterDrawer={openFilterDrawer}
        />
      </div>
      <div
        className={
          isPublicSource
            ? "public-output-analyzer-body"
            : "output-analyzer-body"
        }
      >
        <div className="height-100" key={currentDoc?.document_id}>
          <OutputAnalyzerCard
            doc={currentDoc}
            selectedPrompts={selectedPrompts}
            totalFields={totalFields}
          />
        </div>
      </div>
      <Drawer
        title="Filter Prompt Fields"
        open={isFilterDrawerOpen}
        onClose={closeFilterDrawer}
      >
        <FilterPromptFields
          isOpen={isFilterDrawerOpen}
          selectedPrompts={selectedPrompts}
          setSelectedPrompts={setSelectedPrompts}
        />
      </Drawer>
    </div>
  );
}

export { OutputAnalyzer };
