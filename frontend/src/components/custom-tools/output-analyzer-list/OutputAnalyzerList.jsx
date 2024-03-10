import { OutputAnalyzerHeader } from "../output-analyzer-header/OutputAnalyzerHeader";
import "./OutputAnalyzerList.css";
import { OutputAnalyzerCard } from "../output-analyzer-card/OutputAnalyzerCard";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import { useEffect, useState } from "react";
import { promptType } from "../../../helpers/GetStaticData";

function OutputAnalyzerList() {
  const [totalFields, setTotalFields] = useState(0);
  const { listOfDocs, details } = useCustomToolStore();

  useEffect(() => {
    const prompts = [...(details?.prompts || [])];
    const promptsFiltered = prompts.filter(
      (item) => item?.prompt_type === promptType.prompt
    );
    setTotalFields(promptsFiltered.length || 0);
  }, [details]);

  return (
    <div className="output-analyzer-layout">
      <div>
        <OutputAnalyzerHeader />
      </div>
      <div className="output-analyzer-body">
        {listOfDocs.map((doc) => {
          return (
            <div
              className="output-analyzer-card-gap"
              key={doc?.prompt_document_id}
            >
              <OutputAnalyzerCard doc={doc} totalFields={totalFields} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export { OutputAnalyzerList };
