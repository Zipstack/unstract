import PropTypes from "prop-types";
import { memo } from "react";

import { NotesCard } from "../notes-card/NotesCard";
import { PromptCard } from "./PromptCard";
import { promptType } from "../../../helpers/GetStaticData";
import { useCustomToolStore } from "../../../store/custom-tool-store";
import usePromptRun from "../../../hooks/usePromptRun";
import { usePromptRunStatusStore } from "../../../store/prompt-run-status-store";

const PromptCardWrapper = memo(function PromptCardWrapper({
  item,
  handleChangePromptCard,
  handleDelete,
  outputs,
  enforceTypeList,
  allTableSettings,
  setAllTableSettings,
  setUpdatedPromptsCopy,
  coverageCountData,
  isChallenge,
}) {
  const { isSimplePromptStudio } = useCustomToolStore();
  const { handlePromptRunRequest } = usePromptRun();
  const promptRunStatus = usePromptRunStatusStore(
    (state) => state?.promptRunStatus?.[item?.prompt_id] || {}
  );

  return (
    <div>
      {(item.prompt_type === promptType.prompt || isSimplePromptStudio) && (
        <PromptCard
          promptDetails={item}
          handleChangePromptCard={handleChangePromptCard}
          handleDelete={handleDelete}
          updatePlaceHolder="Enter Prompt"
          promptOutputs={outputs}
          enforceTypeList={enforceTypeList}
          allTableSettings={allTableSettings}
          setAllTableSettings={setAllTableSettings}
          setUpdatedPromptsCopy={setUpdatedPromptsCopy}
          handlePromptRunRequest={handlePromptRunRequest}
          promptRunStatus={promptRunStatus}
          coverageCountData={coverageCountData}
          isChallenge={isChallenge}
        />
      )}
      {item.prompt_type === promptType.notes && (
        <NotesCard
          promptDetails={item}
          handleChangePromptCard={handleChangePromptCard}
          handleDelete={handleDelete}
          updatePlaceHolder="Enter Notes"
          setUpdatedPromptsCopy={setUpdatedPromptsCopy}
        />
      )}
    </div>
  );
});

PromptCardWrapper.displayName = "PromptCardWrapper";

PromptCardWrapper.propTypes = {
  item: PropTypes.object.isRequired,
  handleChangePromptCard: PropTypes.func.isRequired,
  handleDelete: PropTypes.func.isRequired,
  outputs: PropTypes.object.isRequired,
  enforceTypeList: PropTypes.array.isRequired,
  allTableSettings: PropTypes.array.isRequired,
  setAllTableSettings: PropTypes.func.isRequired,
  setUpdatedPromptsCopy: PropTypes.func.isRequired,
  coverageCountData: PropTypes.object.isRequired,
  isChallenge: PropTypes.bool.isRequired,
};

export { PromptCardWrapper };
