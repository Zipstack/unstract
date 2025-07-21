import { usePostHog } from "posthog-js/react";

import { useSessionStore } from "../store/session-store";

const usePostHogEvents = () => {
  const posthog = usePostHog();
  const { sessionDetails } = useSessionStore();

  const posthogEventText = {
    llm: "intent_add_llm",
    vector_db: "intent_add_vectordb",
    embedding: "intent_add_embedding",
    x2text: "intent_add_text_extractor",
    ocr: null,
  };

  const posthogTcEventText = {
    llm: "test_connection_llm",
    vector_db: "test_connection_vectordb",
    embedding: "test_connection_embedding",
    x2text: "test_connection_text_extractor",
    ocr: null,
  };

  const posthogSubmitEventText = {
    llm: "intent_success_add_llm",
    vector_db: "intent_success_add_vectordb",
    embedding: "intent_success_add_embedding",
    x2text: "intent_success_add_text_extractor",
    ocr: null,
  };

  const posthogConnectorEventText = {
    "FILESYSTEM:input": "intent_wf_fs_source",
    "FILESYSTEM:output": "intent_wf_fs_dest",
    "DATABASE:output": "intent_wf_db_dest",
  };

  const posthogConnectorAddedEventText = {
    "FILESYSTEM:input": "intent_success_wf_fs_source",
    "FILESYSTEM:output": "intent_success_wf_fs_dest",
    "DATABASE:output": "intent_success_wf_db_dest",
  };

  const posthogWfDeploymentEventText = {
    API: "wf_deploy_api",
    ETL: "wf_deploy_etl",
    TASK: "wf_deploy_task",
  };

  const posthogDeploymentEventText = {
    api: "intent_api_deployment",
    api_success: "intent_success_api_deployment",
    etl: "intent_etl_deployment",
    etl_success: "intent_success_etl_deployment",
    task: "intent_task_deployment",
    task_success: "intent_success_task_deployment",
  };

  const setPostHogIdentity = () => {
    const distinctId = `${sessionDetails?.orgId}:${sessionDetails?.orgName}`;
    const orgName = sessionDetails?.orgName;
    const isOpenSource = orgName === "mock_org";

    const name = `${sessionDetails?.name} ${sessionDetails?.family_name || ""}`;
    const optionalParams = {
      name,
      org: orgName,
      software: isOpenSource ? "OSS" : "SAAS",
    };

    const email = sessionDetails?.email;
    const userId = sessionDetails?.id;

    if (email) {
      optionalParams["email"] = email;
    } else {
      optionalParams["userId"] = userId;
    }

    posthog.identify(distinctId, optionalParams);
  };

  const setPostHogCustomEvent = (distinctId, optionalParams) => {
    posthog.capture(distinctId, optionalParams);
  };

  return {
    posthogEventText,
    posthogTcEventText,
    posthogSubmitEventText,
    posthogConnectorEventText,
    posthogConnectorAddedEventText,
    posthogWfDeploymentEventText,
    posthogDeploymentEventText,
    setPostHogIdentity,
    setPostHogCustomEvent,
  };
};

export default usePostHogEvents;
