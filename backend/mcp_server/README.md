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
| Tools | extract, poll status | extract, plus discovery, observability, state changes and Prompt Studio |

The split is not cosmetic. A deployment key grants exactly one workflow and
resolves to no user, so it cannot authorize anything organization-wide; a
platform key resolves to a service-account user and is checked by the shared
auth middleware. Neither key works on the other server.

**Both servers run extraction, and that is deliberate.** They are two blast
radii for the same operation. A deployment key reaches one deployment, so a
leaked one costs one workflow — but obtaining it is a separate step, and the
platform server cannot hand it over (key retrieval is excluded, see below). A
platform key reaches every deployment in the organization and needs no second
credential. Requiring the narrow key bought no safety when the platform server
already spends money through `executePipeline` and Prompt Studio; it only made
extraction awkward to reach. Pick whichever tradeoff you want.

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

`GET` on either URL answers `405 Method Not Allowed` with `Allow: POST`. Under
Streamable HTTP a client issues `GET` to open a server-to-client SSE stream,
and a server that offers none must decline — every tool call here is
request/response, so there is nothing to stream. The 405 still carries a small
server-identity body for uptime probes and humans with `curl`; it is
unauthenticated and reveals nothing about the deployment behind it.

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

**Discovery** — what exists:

| Tool | Tier | Purpose |
| --- | --- | --- |
| `readMeFirst` | read | Orientation, including what this credential can reach. |
| `whoami` | read | The key's organization, tier, and remaining spend budget. |
| `listApiDeployments` | read | Deployed extraction endpoints, with their `api_name`. |
| `listWorkflows` | read | The workflows behind them. |
| `listPipelines` | read | ETL and task pipelines, with schedule and last-run state. |
| `listPromptStudioProjects` | read | Where extraction prompts are authored. |
| `listPromptStudioDocuments` | read | Documents in a project. The only source of `document_id`. |
| `listPrompts` | read | A project's prompts. The only source of `prompt_id`. |
| `getWorkflowEndpoints` | read | How a workflow is wired — shape only, never config. |
| `listToolInstances` | read | The tool steps inside a workflow. |
| `listTags` | read | Execution tags. |

**Observability** — what happened:

| Tool | Tier | Purpose |
| --- | --- | --- |
| `listExecutions` | read | Recent runs and their status. Start here to debug. |
| `getExecutionDetail` | read | Per-file results and errors for one run. |
| `getUsageSummary` | read | Tokens and cost recorded so far. |
| `getExecutionStatus` | read | Poll an extraction started by `extractDocument`. |

**State changes** — cheap, reversible:

| Tool | Tier | Purpose |
| --- | --- | --- |
| `setApiDeploymentActive` | `read_write` | Take a deployment offline, or bring it back. |
| `setPipelineActive` | `read_write` | Pause or resume a pipeline's schedule. |

**Billable** — each call costs real money, and is budgeted:

| Tool | Tier | Purpose |
| --- | --- | --- |
| `executePipeline` | `read_write` | Trigger a real pipeline run. |
| `indexDocument` | `read_write` | Embed a document so prompts can run against it. |
| `fetchResponse` | `read_write` | Run one prompt against an indexed document. |
| `bulkFetchResponse` | `read_write` | Run several prompts in one pass. |
| `singlePassExtraction` | `read_write` | Run a project's whole prompt set. |
| `extractDocument` | `read_write` | Run a named deployment's extraction workflow. |

To extract a document through a *deployed* API, an agent calls
`listApiDeployments` for an `api_name`, then `extractDocument` with that name —
no second credential and no second session. Polling is free: `getExecutionStatus`
is a read tool, so an agent waiting on a result never spends budget to check on
it. The Prompt Studio tools are for working with prompts *before* they are
deployed; `extractDocument` runs what is already deployed.

Two things differ from the same tool on the deployment server, both because the
caller is org-scoped rather than deployment-scoped:

- **`api_name` is a required argument.** The deployment server learns its target
  from the credential; here the agent names it.
- **`llm_profile_id` is not offered.** That argument is validated against the
  API key's owner, and a platform key resolves to a service account with no
  meaningful owner to check against. Supplying some deployment's key to satisfy
  the check would assert a principal the caller is not, so the argument is
  dropped instead. Pinned by `test_registry_reachability.py`, because the
  coupling is otherwise invisible: the field is what would make the serializer
  read an `api_key` this context does not have.

`getExecutionStatus` re-checks the execution against the organization before
returning it. `DeploymentHelper.get_execution_status` does a bare lookup by id
with no tenant filter, and this deployment runs one shared schema rather than a
schema per tenant, so the check is made here rather than assumed.

## The spend guard

The billable tools drive LLM inference, embedding and vector-store writes. An
agent looping over a list, or retrying on a misread error, can spend a great
deal without anyone watching — so they are budgeted per organization over a
rolling window (`MCP_BILLABLE_CALL_LIMIT`, default 50 per
`MCP_BILLABLE_WINDOW_SECONDS`, default one hour).

**A call that could never have run does not cost a slot.** The budget is
consumed on invocation and never refunded, which is right for a call that may
have spent tokens upstream — but wrong for one refused on an argument the
server could check for free. Every billable tool therefore declares a
`preflight` that resolves its target (the deployment, project or pipeline it
names) *before* the budget is claimed. This matters most for `extractDocument`,
whose `api_name` is caller-supplied prose rather than an id copied from a
listing: without it, an agent guessing at names could exhaust the window
without ever reaching an LLM. `test_spend_guard.py` fails if a billable tool is
registered without one.

**It counts calls, not tokens or currency.** Unstract's open-source backend
records usage after the fact but has no pre-flight allowance to check against —
subscription and quota enforcement live in the enterprise overlay, which this
app cannot depend on. A call counter is the strongest guard implementable here,
and it is a blunt one: it bounds how *often* an agent triggers paid work, not
how expensive each call is.

Three behaviours are deliberate:

- **Budget is consumed on invocation and never refunded**, including when the
  tool then fails. A Prompt Studio call that fails partway may already have
  spent tokens upstream, and refunding on failure would let an agent burn
  unbounded spend by failing in a loop. This is the opposite of the rate-limit
  slot in `tools/execution.py`, which models concurrency rather than cost.
- **Exhaustion is temporary, not a permission error.** It comes back as an
  `isError` result naming when to retry, so the agent waits rather than
  concluding the tool is forbidden.
- **It fails open.** If the cache is unavailable the call is allowed and the
  event logged. This guard bounds runaway loops; it is not a licence check, and
  taking the whole MCP surface offline because Redis blipped would be worse.

`whoami` reports the remaining budget so an agent can pace itself instead of
discovering the limit by hitting it.

### Where the counter lives

One key per organization, `mcp:billable:<org_id>`, expired by TTL — there is no
window-start timestamp, so the window begins at the first billable call rather
than at a wall-clock boundary. `cache.add` initialises the counter without
disturbing an in-flight window, and `cache.incr` is atomic, so concurrent
requests cannot race past the limit.

`MCP_REDIS_DB` selects the Redis DB and **defaults to `REDIS_DB`**, so out of
the box MCP state shares the general cache DB and behaves like any other cache
user — including honouring `override_settings(CACHES=...)` in tests. Set it only
to move MCP state onto its own DB; the guard then builds a client for that DB,
preferring a `CACHES["mcp"]` alias if one is configured. The knob exists so that
move is available later without being a breaking change.

Note the consequence of the default: sharing DB 0 means a `FLUSHDB` or a
cache-wide eviction resets every organization's window. That is a fail-open
outcome, consistent with the rest of the guard's design — this is a loop
bound, not an audited ledger.

## How write tools are authorized

Platform API key tiers are defined in terms of HTTP methods
(`ApiKeyPermission.allows`), but every JSON-RPC message arrives as an HTTP
`POST` whatever the tool inside it does — so the auth middleware's tier check
cannot tell `listWorkflows` from `executePipeline`.

Each tool therefore declares the method its REST equivalent would use
(`required_method`), and `check_tool_allowed` re-applies the key's tier against
*that*. This reuses the semantics the codebase already enforces instead of
inventing a parallel scheme, and it means a tool marked `DELETE` is
`full_access`-only for the same reason a REST `DELETE` is.

A `writes=True` tool left at the default `required_method="GET"` would slip past
that guard, so a test asserts none exists.

## What is deliberately not exposed

The platform has a much larger API surface than this server wraps. What is left
out is left out on purpose, and falls into three groups.

### Anything whose response carries a credential

Several subsystems return decrypted secrets as part of their ordinary
responses — connector configuration includes the credentials used to reach the
source system, adapter configuration includes the provider API key, notification
configuration includes the webhook's authorization token, and the key-management
endpoints return key material by design.

**No tool wraps any of them.** An agent's context is not a safe place for a
credential: it is logged, it may be replayed to a model provider, and an agent
processing an untrusted document can be induced to repeat what it has seen.

Concretely, this server has no tool for:

- connector or adapter configuration (`listConnectors`, `getAdapter`, …)
- platform, deployment, or platform-API key management — including **creating
  or rotating** a key, which returns the new secret in its response
- notification / webhook configuration
- the Postman collection export, which embeds a live API key

Two mechanisms keep this true as tools are added:

- `test_no_credential_leak.py` seeds an organization with recognizable fake
  secrets, invokes **every** read tool in the registry, and fails if any of them
  appears in the output. New tools are covered the moment they are registered.
- A test asserts that no tool name suggests credential handling, and none
  suggests connector or adapter access.

Where a tool must touch something adjacent to a credential, it names the fields
it returns rather than serializing a model. `getWorkflowEndpoints` is the case
to look at: a workflow endpoint points at a connector instance, so the tool
returns the *shape* of the connection — endpoint type, connection type,
connector name — and never the configuration. Free-form error text from failed
executions is additionally passed through `redact_secrets`, because a failing
connector reports the connection string it tried.

### Destructive operations

Deleting a workflow, deployment, Prompt Studio project, tag or connector
destroys work that no inverse call restores; so does removing organization
members. Every write tool here is reversible by construction — the opposite call
puts things back — and `required_method="DELETE"` exists so that if a
destructive tool is ever added it is `full_access`-only from the start.

Also excluded: password resets, role assignment and revocation, and member
removal. These change who can access the organization, which is not a decision
to delegate to an agent.

### Endpoints that reach out to a caller-influenced host

The connector and adapter *test* endpoints exist to verify a configuration by
making a live outbound call to the host it names. Exposing them would hand any
platform API key a request-forgery primitive: the agent chooses the
destination, the server makes the call from inside the deployment's network,
and the response comes back. That the same endpoints also take credentials as
*input* is a second reason, but the outbound call is the disqualifying one.

Prompt Studio project **import** is excluded on the same grounds — it ingests a
bundle the caller supplies. **Export** is excluded because a project bundle may
carry adapter references, which is the credential rule above applied to a file
rather than a JSON field.

### Workflow endpoint and tool-instance *configuration*

Reading the shape of a workflow's endpoints is exposed
(`getWorkflowEndpoints`, `listToolInstances`); writing it is not. Endpoint
configuration is where connector instances are bound to a workflow, so a write
there redirects where a workflow reads its input from and writes its output to
— without changing anything that a later read would show as unusual. That is a
data-exfiltration path dressed as a settings change, so it stays out.

### Everything else, for now

Not excluded on principle, simply not built: file upload/download, and Prompt
Studio project and prompt *authoring*. The coherent scope of this server is
that an agent operates on projects and documents a human has already set up —
it can discover them, run them, and read the results, but it does not create
the raw material. These are candidates for later, with the same rules applied.

Document and prompt *listing* used to sit in this section. It has since been
built (`listPromptStudioDocuments`, `listPrompts`) because it was not a nicety:
those two tools are the only source of the `document_id` and `prompt_id` that
every billable Prompt Studio tool requires, so without them those tools were
listed but uncallable. `tests/test_registry_reachability.py` now fails if any
tool requires an id that no tool is declared to produce.

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
gates on HTTP method, and every JSON-RPC message is a `POST`, which `read`
disallows —
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

**Never** build a response with `serializer.data`, `model_to_dict`, or a `**`
splat. Name every field. Several models decrypt credentials on attribute
access, so wholesale serialization is how a secret escapes — see the exclusion
list above.

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

For a tool that costs money, also set `billable=True`. That flag is the only
thing wiring it into the spend guard, so forgetting it leaves the tool
unbudgeted — `test_spend_guard.py` names the tools that must carry it.

If a tool returns free-form text that originates outside this app (an error
message, a log line), pass it through `redact_secrets` first.

---

## Not implemented

OAuth 2.1 with dynamic client registration, which MCP defines for browser-based
one-click connectors. Bearer auth covers Claude Code and API clients on both
servers. Adding OAuth is additive — it would mount discovery endpoints
alongside these routers without changing the transport.
