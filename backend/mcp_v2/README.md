# Hosted MCP server

Exposes an Unstract API deployment to coding agents over the
[Model Context Protocol](https://modelcontextprotocol.io), so an agent can run
document extraction as a tool call instead of hand-rolling HTTP requests.

The server is hosted inside the existing backend — it is a Django app served by
the same gunicorn process, not a separate service to deploy or scale.

## Endpoint

An MCP session is scoped to exactly one API deployment, and mirrors the URL
shape of that deployment's REST endpoint:

```
POST /deployment/api/<org_name>/<api_name>/     # REST
POST /mcp/<org_name>/<api_name>/                # MCP
```

Authentication is the deployment's **existing API key** — the same key used for
REST execution, managed from the same place in the UI. There is no separate MCP
credential to mint or revoke.

```
Authorization: Bearer <api_key>
```

For MCP clients that cannot attach custom headers, the key may instead be given
as a path segment:

```
POST /mcp/<org_name>/<api_name>/<api_key>/
```

The path key takes precedence over the header when both are present.

`GET` on either URL returns server identity for clients that probe before
connecting. It is unauthenticated and reveals nothing about the deployment.

## Connecting

With Claude Code:

```bash
claude mcp add --transport http unstract \
  https://<host>/mcp/<org_name>/<api_name>/ \
  --header "Authorization: Bearer <api_key>"
```

## Tools

| Tool | Purpose |
| --- | --- |
| `readMeFirst` | Orientation guide, built from the live deployment. Call first. |
| `getApiInfo` | Name, description, workflow and active state of the deployment. |
| `extractDocument` | Run extraction over document URLs. **Consumes quota.** |
| `getExecutionStatus` | Poll for the result of a pending extraction. |

Documents are passed as **S3 pre-signed URLs** and fetched server-side; the
execution serializer rejects anything else, so a plain public link will not
work. Extraction is asynchronous:
`extractDocument` returns an `execution_id` when it does not finish within the
timeout, and the agent polls `getExecutionStatus` with it.

## Adding a tool

Write a handler taking `MCPContext` as its first argument, then register it in
`registry.py` with a JSON schema:

```python
registry.register(
    MCPTool(
        name="myTool",
        description="What it does, written for an LLM to read.",
        input_schema={"type": "object", "properties": {...}, "required": [...]},
        handler=my_tool,
        writes=False,
    )
)
```

Tool descriptions are prompts, not documentation — they are the only guidance
the calling agent gets. Say what the tool does, when to use it, and what it
costs.

Raise `MCPToolError` for failures the agent can act on (bad arguments, inactive
deployment, rate limit); the message reaches the agent verbatim, so write it as
an instruction. Any other exception is logged and reported generically so
internal detail does not leak to the client.

## Design notes

- **Auth reuses the deployment key path.** `_resolve_context` calls the same
  `DeploymentHelper` validation the REST endpoint uses, so the two surfaces
  cannot drift apart on who is allowed in.
- **Execution reuses `ExecutionRequestSerializer`.** URL validation and the
  file-count cap live there; reimplementing them for MCP would let the MCP
  surface quietly diverge from the REST one.
- **All auth failures answer identically** (401, no detail), so the endpoint
  cannot be used to enumerate deployment names.
- **Tool errors are JSON-RPC results, not protocol errors.** Clients treat
  protocol errors as unrecoverable transport faults; an agent-fixable problem
  comes back as `isError: true` content it can read and retry.

## Not implemented

OAuth 2.1 with dynamic client registration, which MCP defines for browser-based
one-click connectors. Header/path bearer auth covers Claude Code and
API clients. Adding OAuth is additive — it would mount discovery endpoints
alongside this router without changing the transport.
