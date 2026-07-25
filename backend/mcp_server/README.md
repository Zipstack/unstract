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
| URL | `/deployment/api/<org>/<api_name>/mcp` | `/api/v1/unstract/<org>/mcp/` |
| Tools | extract, poll status | discovery + state changes |

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
POST /deployment/api/<org_name>/<api_name>/mcp  # MCP
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
POST /deployment/api/<org_name>/<api_name>/mcp/<api_key>/
```

The path key takes precedence over the header when both are present.

`GET` on either URL returns server identity for clients that probe before
connecting. It is unauthenticated and reveals nothing about the deployment.

## Connecting

With Claude Code:

```bash
claude mcp add --transport http unstract \
  https://<host>/deployment/api/<org_name>/<api_name>/mcp \
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

Organization-scoped: an agent can discover what exists in an Unstract
organization — deployments, workflows, pipelines, Prompt Studio projects — and
change the running state of those resources.

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

| Tool | Tier | Purpose |
| --- | --- | --- |
| `readMeFirst` | read | Orientation, including what this credential can reach. |
| `whoami` | read | The key's organization, tier and what it may do. |
| `listApiDeployments` | read | Deployed extraction endpoints, with their `api_name`. |
| `listWorkflows` | read | The workflows behind them. |
| `listPipelines` | read | ETL and task pipelines, with schedule and last-run state. |
| `listPromptStudioProjects` | read | Where extraction prompts are authored. |
| `setApiDeploymentActive` | `read_write` | Take a deployment offline, or bring it back. |
| `setPipelineActive` | `read_write` | Pause or resume a pipeline's schedule. |
| `executePipeline` | `read_write` | Trigger a real pipeline run. **Consumes quota.** |

To actually extract a document, an agent calls `listApiDeployments` to find an
`api_name`, then opens a **separate** session against the deployment server
above.

## How write tools are authorized

Platform API key tiers are defined in terms of HTTP methods
(`ApiKeyPermission.allows`), but every MCP call is a `POST` — so the auth
middleware's tier check cannot tell `listWorkflows` from `executePipeline`.

Each tool therefore declares the method its REST equivalent would use
(`required_method`), and `check_tool_allowed` re-applies the key's tier against
*that*. This reuses the semantics the codebase already enforces instead of
inventing a parallel scheme, and it means a tool marked `DELETE` is
`full_access`-only for the same reason a REST `DELETE` is.

A `writes=True` tool left at the default `required_method="GET"` would slip past
that guard, so a test asserts none exists.

## What is deliberately not exposed

**Credential operations.** Creating or rotating an API key returns the secret in
its response. An MCP tool for it would hand an agent — one that may be
processing untrusted document content — a way to mint or exfiltrate credentials.
The codebase already reasons this way: see `CanRotatePlatformApiKey`'s docstring
on why rotation is `full_access`-only. A test asserts no tool name suggests
credential handling.

**Deletions.** Removing a workflow, deployment or Prompt Studio project destroys
work that no inverse call restores. Every write tool here is reversible by
construction — the opposite call puts things back.

## Why the URL matters

This server is mounted under the tenant prefix, next to `platform-api/`, and
**not** under the deployment prefix. `WHITELISTED_PATHS` is matched with
`startswith`, so everything under `/deployment/...` — including the deployment
MCP server — is exempt from `CustomAuthMiddleware`, while
`/api/v1/unstract/<org>/mcp/` is not. That is exactly how this server inherits
platform-key authentication.

Moving these URLs under the whitelisted prefix would silently remove all
authentication. `test_platform_auth.py::test_the_endpoint_is_not_whitelisted`
guards against that.

Because auth lives in middleware, its tests go through `django.test.Client` and
the real URL. A test using `APIRequestFactory` or calling the view directly
bypasses the middleware and would pass against a completely open endpoint.

## Two constraints worth knowing

**A `read`-tier key cannot use this server at all.** The middleware's tier check
gates on HTTP method, and every MCP call is a `POST`, which `read` disallows —
so a read-only key is refused before reaching the view, even for the read tools.
Use a `read_write` key. Changing that would mean special-casing MCP paths in the
middleware, which is a decision for maintainers rather than something this app
should do unilaterally.

**These tools reach the whole organization.** A platform key resolves to a
service account, and `is_service_account=True` makes `for_user()` managers
return `self.all()` — so it ignores per-user sharing regardless of the `USER`
role the key was created with. For reads that is a disclosure caveat; for
writes it means the key can modify *any* org resource. `whoami`, `readMeFirst`
and every write tool's description say so.

## Adding a tool here

Same registry mechanics as the deployment server, with `PlatformMCPContext`
(`user`, `platform_key`, `org_name`, `request`) as the first argument. Query
through the model's `for_user(context.user)` manager so the platform's own
visibility rules apply, and cap listings — `LIST_LIMIT` with a `truncated` note,
never silent truncation.

For a write tool, also:

- set `writes=True` and a `required_method` (`"POST"` for a mutation, `"DELETE"`
  for anything destructive — that makes it `full_access`-only);
- resolve the target through `for_user` so a caller cannot reach another
  organization's resource, and raise `MCPToolError` naming the list tool when it
  is not found;
- include `_ORG_WIDE_WARNING` in the description — the description is the prompt
  the agent reads before acting, and the service-account caveat matters more
  here than anywhere else;
- return `changed: False` rather than silently succeeding on a no-op, so an
  agent can tell "I did this" from "this was already so".

---

## Not implemented

OAuth 2.1 with dynamic client registration, which MCP defines for browser-based
one-click connectors. Bearer auth covers Claude Code and API clients on both
servers. Adding OAuth is additive — it would mount discovery endpoints
alongside these routers without changing the transport.
