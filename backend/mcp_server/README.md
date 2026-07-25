# Hosted MCP servers

Exposes Unstract to coding agents over the
[Model Context Protocol](https://modelcontextprotocol.io), so an agent can
discover and run document extraction as tool calls instead of hand-rolling HTTP
requests.

Both servers are hosted inside the existing backend — Django views served by the
same gunicorn process, not separate services to deploy or scale. They share the
JSON-RPC transport in `transport.py` and differ only in how a caller is
authenticated and which tools they expose.

| | Deployment server | Platform server |
| --- | --- | --- |
| Scope | one API deployment | one organization |
| Credential | that deployment's API key | a platform API key |
| Authenticated by | the view itself | `CustomAuthMiddleware` |
| URL | `/mcp/<org>/<api_name>/` | `/api/v1/unstract/<org>/mcp/` |
| Tools | extract, poll status | read-only discovery |

The split is not cosmetic. A deployment key grants exactly one workflow and
resolves to no user, so it cannot authorize anything organization-wide; a
platform key resolves to a service-account user and is checked by the shared
auth middleware. Neither key works on the other server.

---

# Deployment server

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

- **Auth reuses the deployment key path.** `resolve_context` calls the same
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

---

# Platform server

Organization-scoped and **read-only**: it lets an agent discover what exists in
an Unstract organization — deployments, workflows, Prompt Studio projects — but
cannot run or change anything.

## Endpoint

```
POST /api/v1/unstract/<org_name>/mcp/
Authorization: Bearer <platform_api_key>
```

```bash
claude mcp add --transport http unstract-platform \
  https://<host>/api/v1/unstract/<org_name>/mcp/ \
  --header "Authorization: Bearer <platform_api_key>"
```

Platform API keys are managed at `/api/v1/unstract/<org>/platform-api/keys/`.

## Tools

| Tool | Purpose |
| --- | --- |
| `readMeFirst` | Orientation, including what this credential can see. |
| `whoami` | The key's organization, permission tier and visibility scope. |
| `listApiDeployments` | Deployed extraction endpoints, with their `api_name`. |
| `listWorkflows` | The pipelines behind them. |
| `listPromptStudioProjects` | Where extraction prompts are authored. |

To actually extract, an agent calls `listApiDeployments` to find an `api_name`,
then opens a **separate** session against the deployment server above.

## Why the URL matters

This server is mounted under the tenant prefix, next to `platform-api/`, and
**not** under `MCP_PATH_PREFIX`. `WHITELISTED_PATHS` is matched with
`startswith`, so `/mcp/...` is exempt from `CustomAuthMiddleware` while
`/api/v1/unstract/<org>/mcp/` is not — which is exactly how this server
inherits platform-key authentication.

Moving these URLs under the whitelisted prefix would silently remove all
authentication. `test_platform_auth.py::test_the_endpoint_is_not_whitelisted`
guards against that.

Because auth lives in middleware, its tests go through `django.test.Client` and
the real URL. A test using `APIRequestFactory` or calling the view directly
bypasses the middleware and would pass against a completely open endpoint.

## Two constraints worth knowing

**A `read`-tier key cannot use this server at all.** The middleware's tier check
gates on HTTP method, and every MCP call is a `POST`, which `read` disallows —
so a read-only key is refused before reaching the view, even though every tool
here is read-only. Use a `read_write` key. Changing that would mean special-
casing MCP paths in the middleware, which is a decision for maintainers rather
than something this app should do unilaterally.

**These tools see the whole organization.** A platform key resolves to a service
account, and `is_service_account=True` makes `for_user()` managers return
`self.all()` — so listings ignore per-user sharing regardless of the `USER` role
the key was created with. `whoami` and `readMeFirst` both say so, because an
agent that assumed otherwise would draw wrong conclusions from a listing.

## Adding a tool here

Same registry mechanics as the deployment server, with `PlatformMCPContext`
(`user`, `platform_key`, `org_name`) as the first argument. Query through the
model's `for_user(context.user)` manager so the platform's own visibility rules
apply, and cap results — `LIST_LIMIT` with a `truncated` note, never silent
truncation.

Write tools are deliberately absent. `check_tool_allowed` already refuses a
`writes=True` tool to a `read`-tier key, so the guard is in place, but the
read-only promise is pinned by
`test_platform_tier_guard.py::test_platform_registry_is_entirely_read_only` —
adding a write tool will fail that test and force a deliberate decision about
whether an agent should hold that power.

---

## Not implemented

OAuth 2.1 with dynamic client registration, which MCP defines for browser-based
one-click connectors. Bearer auth covers Claude Code and API clients on both
servers. Adding OAuth is additive — it would mount discovery endpoints
alongside these routers without changing the transport.
