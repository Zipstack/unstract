import { useSessionStore } from "../../../store/session-store";
import { PromptRunAsync } from "./PromptRunAsync";
import { PromptRunSync } from "./PromptRunSync";

function PromptRun() {
  const { sessionDetails } = useSessionStore();
  const isAsync = !!sessionDetails?.flags?.async_prompt_execution;

  return isAsync ? <PromptRunAsync /> : <PromptRunSync />;
}

export { PromptRun };
