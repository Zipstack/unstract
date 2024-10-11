import { useEffect, useState } from "react";

import { OutputAnalyzerHeader } from "../output-analyzer-header/OutputAnalyzerHeader";
import "./OutputAnalyzer.css";
import { OutputAnalyzerCard } from "../output-analyzer-card/OutputAnalyzerCard";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { promptType } from "../../../helpers/GetStaticData";

function OutputAnalyzer() {
  const [totalFields, setTotalFields] = useState(0);
  const [currentDocIndex, setCurrentDocIndex] = useState(0);
  const { listOfDocs, details, isPublicSource } = useCustomToolStore();

  useEffect(() => {
    handleTotalFields();
  }, []);

  const handleTotalFields = () => {
    const prompts = [...(details?.prompts || [])];
    const promptsFiltered = prompts.filter(
      (item) => item?.prompt_type === promptType.prompt
    );
    setTotalFields(promptsFiltered.length || 0);
  };

  return (
    <div className="output-analyzer-layout">
      <div>
        <OutputAnalyzerHeader
          docs={listOfDocs}
          currentDocIndex={currentDocIndex}
          setCurrentDocIndex={setCurrentDocIndex}
        />
      </div>
      <div
        className={
          isPublicSource
            ? "public-output-analyzer-body"
            : "output-analyzer-body"
        }
      >
        <div
          className="height-100"
          key={listOfDocs[currentDocIndex]?.document_id}
        >
          <OutputAnalyzerCard
            doc={listOfDocs[currentDocIndex]}
            totalFields={totalFields}
          />
        </div>
      </div>
    </div>
  );
}

export { OutputAnalyzer };
