import { Typography } from "@/components/ui/shims/antd-typography";

import { ApiKeyManager } from "../api-key-manager/ApiKeyManager.jsx";

/**
 * Key management for the Agent-KV extraction API.
 *
 * A thin wrapper over `ApiKeyManager`, like `PlatformApiKeys` and
 * `GlobalApiDeploymentKeys`: the shared screen owns the table and the
 * create/edit/rotate/delete/copy flows, and the only thing that differs here
 * is the resource path and the fact that there is nothing extra to collect —
 * an Agent-KV key carries no permission tier and no deployment scope, so
 * neither `extraColumns` nor the field hooks are passed.
 *
 * `resourcePath` resolves to `/api/v1/unstract/{orgId}/agent-kv/keys/`
 * (`backend/agent_kv/urls.py`, mounted in `urls_v2.py`). That is the
 * tenant-scoped, session-authenticated management surface — NOT the public
 * `/agent-kv/` execution prefix the resulting key is then used against, which
 * is whitelisted out of the session middleware and authenticates with the key
 * itself.
 */
function AgentKvKeys() {
  return (
    <ApiKeyManager
      title="Agent-KV API Keys"
      entityLabel="Agent-KV API Key"
      resourcePath="agent-kv"
      renderCreateFields={() => (
        <Typography.Text type="secondary">
          Send this key as <code>Authorization: Bearer &lt;key&gt;</code> when
          calling the Agent-KV extraction API. It is shown in full once, here
          and on rotate; the list only ever shows the last four characters.
        </Typography.Text>
      )}
    />
  );
}

export { AgentKvKeys };
