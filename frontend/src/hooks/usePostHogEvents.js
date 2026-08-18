import { usePostHog } from "posthog-js/react";

import { isSaasProdDeployment } from "../helpers/PostHogDeployment";
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
    FILESYSTEM: "intent_success_fs_connector",
    DATABASE: "intent_success_db_connector",
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
    try {
      const orgId = sessionDetails?.orgId;
      const orgName = sessionDetails?.orgName;
      const isOpenSource = orgName === "mock_org";
      const software = isOpenSource ? "OSS" : "SAAS";
      const email = sessionDetails?.email;
      const userId = sessionDetails?.id;

      // PII (email, name) may only leave Unstract-managed SaaS; self-hosted
      // and OSS installs identify with an anonymous org-scoped id instead.
      // Email as distinct_id since bare user ids collide across
      // regions/self-hosts — every deployment reports to one PostHog project
      const canSendPii = isSaasProdDeployment() && !isOpenSource;
      const fallbackId = orgId ? `${orgId}:${userId}` : userId?.toString();
      const distinctId = canSendPii && email ? email : fallbackId;

      const personProperties = {
        org: orgName,
        software,
      };

      if (canSendPii) {
        personProperties.name =
          `${sessionDetails?.name} ${sessionDetails?.family_name || ""}`.trim();
        if (email) {
          personProperties.email = email;
        }
      }
      if (userId) {
        personProperties.userId = userId;
      }

      posthog.identify(distinctId, personProperties);

      // Super-properties ride on every captured event, enabling org-level
      // breakdowns without the group analytics add-on
      posthog.register({
        org_id: orgId,
        org_name: orgName,
        software,
      });
    } catch (error) {
      console.error("PostHog identify failed:", error);
    }
  };

  const setPostHogCustomEvent = (eventName, properties) => {
    try {
      posthog.capture(eventName, properties);
    } catch {
      // PostHog tracking is non-critical, safe to ignore
    }
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
