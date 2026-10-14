# Organisation capability permissions

An organisation admin decides, per capability, whether **any member** or
**only admins** may use it (UN-4399, Frontend v1 PB-T04). This README and the
`@extend_schema` annotations on `organization_capabilities` are the published
contract; the convention is the one PB-T01 set (`platform_audit/README.md`).

## Endpoint

`/api/v1/unstract/{org_id}/organization/capabilities/`

| Method | Who | Does |
|---|---|---|
| GET | any authenticated member, and platform-key service accounts | every capability, its setting, and whether it lets the caller use it |
| PATCH | organisation admins on a session (not service accounts) | sets any subset; returns the same shape as GET |

### GET

```json
{
  "capabilities": [
    {
      "key": "create_connectors",
      "label": "Create connectors",
      "description": "Add new source and destination connectors.",
      "setting": "any_member",
      "allowed_for_me": true
    }
  ]
}
```

Always all seven, in this order:

| `key` | Default | Governs |
|---|---|---|
| `create_llm_adapters` | `any_member` | creating an LLM adapter |
| `create_connectors` | `any_member` | creating a connector |
| `create_other_adapters` | `any_member` | creating any non-LLM adapter (embedding, vector DB, text extractor, OCR) |
| `manage_api_keys` | `admins_only` | creating and rotating platform keys and global deployment keys (not per-deployment keys, which their owners manage) — **not yet enforced, see below** |
| `manage_members` | `admins_only` | inviting members and changing roles — **not yet enforced** |
| `change_platform_defaults` | `admins_only` | organisation-wide platform settings — **not yet enforced** |
| `delete_workflows_and_deployments` | `any_member` | deleting a workflow, API deployment or pipeline |

`allowed_for_me` means *the setting does not block you*. It is always true for
admins. For service accounts it is true for the enforced capabilities and false
for the three not yet enforced, whose endpoints refuse service accounts today.
Changing an adapter's type counts as creating one of the new type. Object
rules still apply on top: with
`any_member`, deleting still needs the caller to own (or co-own) the resource,
exactly as before; with `admins_only`, owners who are not admins are refused.

### PATCH

```json
{"create_connectors": "admins_only", "delete_workflows_and_deployments": "admins_only"}
```

Any subset of keys, at least one; each value `admins_only` or `any_member`.
Every key and value is validated before anything is saved. Errors use the
standard envelope (`{type, errors[{code, detail, attr}]}`):

| Status | When |
|---|---|
| 400 | unknown key (`attr` = the key), bad value, empty body, or `any_member` for a capability that is not enforced yet |
| 403 | not an organisation admin, or a service account |
| 404 | no organisation in the request context |

`manage_api_keys`, `manage_members` and `change_platform_defaults` accept only
`admins_only` until their enforcement lands (PR-2 of UN-4399, which waits on
the product decision about what "any member" may do there). Their endpoints
are admin-only today, so storing `any_member` would make `allowed_for_me` lie.

## Refusals

A governed endpoint refuses with **403** in the standard envelope. The detail
is `<label> is restricted to organisation admins.`; the two original
capabilities keep their existing messages ("LLM adapter creation is restricted
to organization admins. …", "Connector creation is restricted to organization
admins. …").

## Storage and the legacy endpoint

Each capability is a `restrict_*` boolean on `Organization` (True = admins
only). `restrict_llm_adapter_creation` and `restrict_connector_creation` are the
storage for the first two, so `organization/settings` (its request and
response unchanged; its audit events are now `capability.changed`) and this
endpoint always agree.

## Audit

Every changed capability writes one `capability.changed` platform audit event
(target `capability`, id = key, name = label, `changes`
`{"before": {"setting": …}, "after": {"setting": …}}`), from either endpoint.

## TypeScript

```ts
type CapabilityKey =
  | "create_llm_adapters" | "create_connectors" | "create_other_adapters"
  | "manage_api_keys" | "manage_members" | "change_platform_defaults"
  | "delete_workflows_and_deployments";
type CapabilitySetting = "admins_only" | "any_member";
interface Capability {
  key: CapabilityKey;
  label: string;
  description: string;
  setting: CapabilitySetting;
  allowed_for_me: boolean;
}
interface CapabilitiesResponse { capabilities: Capability[] }
// At least one key; an empty object is a 400.
type CapabilitiesPatchRequest = Partial<Record<CapabilityKey, CapabilitySetting>>;
```

## For emitters of new enforcement

`tenant_account_v2.capabilities.enforce_capability(request, Capability.X)`
raises the refusal; `RequiresCapability(Capability.X)` is the DRF permission
form. Both skip service accounts. Set the spec's `enforced=True` in the same
change that adds the enforcement.
