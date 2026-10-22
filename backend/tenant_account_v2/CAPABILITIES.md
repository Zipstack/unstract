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
      "allowed_for_me": true,
      "configurable": true
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
| `manage_api_keys` | `admins_only` | creating, viewing and rotating global deployment keys (platform API keys stay admin-only; per-deployment keys are their owners'); see below |
| `manage_members` | `admins_only` | inviting members with the user role; see below |
| `change_platform_defaults` | `admins_only` | the organisation's notification settings (`notifications/settings/`); other defaults are per-user |
| `delete_workflows_and_deployments` | `any_member` | deleting a workflow, API deployment or pipeline |

`allowed_for_me` means *the setting does not block you* — nothing more. It is
always true for admins and for service accounts (platform API keys), which no
capability setting governs. The endpoint's own rules still apply on top and
can refuse a caller this reports as allowed: deleting needs the caller to own
(or co-own) the resource. For the key, member and settings endpoints, see
*What `any_member` allows* below. With `admins_only`, owners who are not
admins are refused.

`configurable` says whether PATCH accepts `any_member` for that capability.
Every capability is configurable now; a capability added later before its
endpoints are ready reports false, and setting it to `any_member` answers 400
"Not configurable yet". A settings UI can lock those rows from it instead of
hard-coding the keys.

Only creation is governed for adapters. Changing an existing adapter's type
counts as creating one of the new type, and that check runs before the request
is validated, so a refused type change answers 403 even when the body has
other errors. An `adapter_type` that is not the registry type of `adapter_id` is
refused with 400, on create and on update (where a missing field falls back to
the stored one), so a provider cannot be filed under the other capability. Any
other edit of an existing adapter, including pointing it at a different
provider of the same type, is not governed.

### PATCH

```json
{"create_connectors": "admins_only", "delete_workflows_and_deployments": "admins_only"}
```

Any subset of keys, at least one; each value `admins_only` or `any_member`.
Every key and value is validated before anything is saved. Errors use the
standard envelope (`{type, errors[{code, detail, attr}]}`):

| Status | When |
|---|---|
| 400 | unknown key (`attr` = the key), bad value or empty body |
| 403 | not an organisation admin, or a service account |
| 404 | no organisation in the request context (GET too) |

### What `any_member` allows for the three admin-only areas

Their endpoints were admin-only. `any_member` lets members in with limits
that keep a member from gaining more than they have; service accounts stay
refused, as before.

- **`manage_members`**: a member may invite with the user role. They may also
  grant another non-admin member a role the auth plugin lets members hand
  out; with the built-in roles that is only the user role, which every
  non-admin already has, so in practice members change no one's role.
  Removing roles, granting or revoking admin, changing an admin's role,
  changing their own role, and removing members stay admin-only. A plugin
  without `is_member_invite_role` refuses every member invite, and one
  without `is_member_assignable_role` every member role grant, so
  `allowed_for_me` can be true while those requests are refused.
- **`manage_api_keys`**: a member may list the global deployment keys they
  created as a member (masked) and create one only for deployments they own (as creator
  or co-owner, the rule for a deployment's own keys), never one for all
  deployments. They may view or rotate only keys they created, under the
  same rule, since both return the secret, and never a key they created
  while an admin (that key is org-level, not bound to them). A key a member
  created may only use LLM profiles its creator owns, like a deployment's own
  key, even after the creator becomes an admin. A key a member created
  (`created_by_member` in the list) stops working once they leave the
  organisation, and for each deployment it names once they stop owning it
  (unless they have since become an org admin). They then cannot rotate it
  either; an admin can deactivate it.
  Setting `manage_api_keys` back to `admins_only` does not disable such keys;
  an admin can deactivate them. An admin cannot add a deployment its creator
  does not own to such a key, or open it to all deployments (400); a new key
  does that. Editing and deleting keys stay admin-only.
  **Platform API keys stay admin-only whatever the setting**:
  each acts as a service account that bypasses per-resource sharing and
  ownership, so a member holding one would reach every resource in the
  organisation. The legacy Settings > Platform keys stay admin-only too.
- **`change_platform_defaults`**: read and change the organisation's
  notification settings. Adapter defaults are per-user and not governed.

`organization/settings` stays admin-only, and so does changing
`organization/capabilities`: changing a capability is never itself a
capability.

This repo's bundled frontend still shows the members, invite and global key
pages to admins only; with `any_member`, members reach member management and
global keys through the API until a frontend reads `allowed_for_me`. The
notification settings already show to members.

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
  configurable: boolean;
}
interface CapabilitiesResponse { capabilities: Capability[] }
// At least one key; an empty object is a 400.
type CapabilitiesPatchRequest = Partial<Record<CapabilityKey, CapabilitySetting>>;
```

## For emitters of new enforcement

`tenant_account_v2.capabilities.enforce_capability(request, Capability.X)`
raises the refusal; `RequiresCapability(Capability.X)` is the DRF permission
form. Neither applies to service accounts. An endpoint that was admin-only
opens to members instead through `opened_to_members`, checked alongside its
admin check; unlike the two above, it refuses service accounts. Set the spec's `enforced=True` in the same
change that adds the enforcement.
