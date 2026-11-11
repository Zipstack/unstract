# Resource usage

Reports what uses each saved adapter and connector: the "Used in" column, the
"used by no workflow" banner and the Usage filter on the adapter and connector
lists, and the usage panel of a profile (Frontend v1 P2-T12).

This README, the `@extend_schema` annotations in `schema.py` and the
serializers in `serializers.py` are the published contract (PB-T11, UN-4328).
Changes to anything below are contract changes.

- [Usage of one profile](#usage-of-one-profile)
- [Usage on the lists](#usage-on-the-lists)
- [What counts as used](#what-counts-as-used)
- [Adding references from another app](#adding-references-from-another-app)

## Usage of one profile

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns |
|---|---|---|
| GET | `adapter/{id}/usage/` | What references the adapter |
| GET | `connector/{id}/usage/` | What references the connector, with the role it plays |

```json
{
  "id": "6f1c…",
  "used_in_count": 1,
  "used_as": "source",
  "groups": {
    "workflows": [
      {
        "id": "a83e…",
        "name": "Invoices",
        "type": "workflow",
        "accessible": true,
        "blocks_delete": true,
        "role": "source"
      }
    ],
    "prompt_studio_projects": [],
    "deployments": [
      {
        "id": "0b2d…",
        "name": "Invoices API",
        "type": "api_deployment",
        "accessible": true,
        "blocks_delete": false,
        "role": "source"
      }
    ],
    "pipelines": []
  }
}
```

- `groups` always has `workflows`, `prompt_studio_projects`, `deployments` and
  `pipelines`, in that order, each possibly empty. Other groups appear only
  when they have items: `other` (see below) and groups the cloud backend adds,
  such as `agentic_studio_projects` and `lookups`.
- `type` says what the item is, so the frontend knows where `id` routes:
  `workflow`, `prompt_studio_project`, `api_deployment`, `pipeline`, or
  `prompt_studio_profile` (a Prompt Studio profile with no project, in
  `other`). Cloud groups add their own values, and any other item in `other`
  carries the referencing model's name, which does not route. The schema
  publishes `type` as an open string for that reason.
- `deployments` and `pipelines` are the API deployments and pipelines of the
  workflows listed under `workflows`. They are listed so the panel can show
  what would stop working, but they are **not** counted in `used_in_count`:
  the workflow already is.
- `blocks_delete` is `true` when this item is why deleting the profile is
  refused. Agentic Studio projects (cloud) are `false`: deleting the adapter
  is allowed and clears it from the project.
- `role` (connectors only) is `source`, `destination`, or `both` when one
  workflow reads from and writes to the same connector.
- `used_as` (connectors only) sums up the roles of the counted items:
  `source`, `destination`, `both` or `none`. `none` means no source or
  destination role, not unused: a connector referenced only from `other` is
  used with `used_as: none`. Read `used_in_count` for used or not.
- Within a group, items the caller can open come first, by name.

**Who may call it.** Anyone who may see the profile: its owners, users and
groups it is shared with, everyone when it is shared to the organisation,
organisation admins and service accounts. Others, and other organisations,
get **404**. One exception: a friction-less adapter is listed for every member,
but its usage follows the rule above, so a member who does not own it and has
no share gets **403**, as for its `adapter_info`.

**Items the caller cannot open** are listed, and counted like any other item,
with `"id": null`,
`"name": null` and `"accessible": false`, so a viewer learns how many things
depend on the profile but not what they are called.

## Usage on the lists

`GET adapter/` and `GET connector/` are **unchanged** unless the caller passes
one of these:

| Parameter | Effect |
|---|---|
| `with_usage=true` | Each row ends with `used_in_count` (and, on connectors, `used_as`). A paged response also ends with `unused_count`. |
| `unused=true` | Lists only profiles with `used_in_count` 0, and adds the same keys. |

Both ignore case; any other value is ignored. They combine with every other
list filter, including `failing` and `last_test_status`.

The paged envelope schema declares `unused_count` (optional). The row keys are
described by the two parameters rather than in the row schema, which is
shared with the lists that do not carry them.

`unused_count` is the number of profiles nothing uses, across all pages. Like
`failing_count`, it applies every list filter except the ones about the count
itself: it ignores `unused`, `failing` and `last_test_status`, so the banner
stays put while the user toggles them.

The usage of every profile the list could show is worked out once per request,
in a fixed number of queries however many profiles or rows there are.

## What counts as used

A profile is used when something references it. The references are the ones
the delete guard refuses on, with the exceptions listed under the table.

| Reference | Group | Blocks delete |
|---|---|---|
| Adapter id, or adapter name before the lazy migration, anywhere in a workflow tool instance's `metadata` | `workflows` | yes |
| Prompt Studio project's summarize, monitor or challenge LLM | `prompt_studio_projects` | yes |
| Prompt Studio profile's LLM, embedding, vector DB or text extractor | `prompt_studio_projects` (the profile's project) | yes |
| Connector on a workflow source or destination | `workflows`, with `role` | yes |
| Any other `PROTECT` or `RESTRICT` foreign key to the profile | `other` | yes |
| Agentic Studio project LLMs and text extractor (cloud) | `agentic_studio_projects` | no |

- The last row of the OSS references is the safety net: a foreign key added
  later that blocks deletion is reported in `other` even before anyone gives it
  a group.
- Agentic Studio references are counted although they don't block deletion,
  so the "used by no workflow" banner never invites deleting an adapter a
  project still relies on.
- Being someone's **default** adapter is not usage. The guard does refuse to
  delete the caller's own default adapter, but that is per user and shown in
  the list's Default column, not here.
- The tool-instance check matches what the delete guard matches, in one query
  per request. The database first narrows the organisation's tool instances
  to those whose `metadata` text contains an adapter's id or name; only those
  are read and walked.

## Adding references from another app

```python
from resource_usage.constants import ProfileKind
from resource_usage.references import Reference, register_provider

def my_refs(adapters):
    ...  # one query for all the adapters given
    yield adapter_pk, Reference(group="my_group", item_type="my_item", model=MyModel,
                                pk=row_pk, name=row_name, blocks_delete=True)

register_provider(ProfileKind.ADAPTER, my_refs, claims=["my_app.MyModel.llm"])
```

Call it from the app's `AppConfig.ready()`. `adapter_pk` is the profile's pk,
as a UUID or its string. On the lists the profiles carry only the viewset's
`usage_fields` columns (`id` and `organization`, and `adapter_name` for
adapters): read only those, or each profile costs a query. `claims` lists each
`PROTECT`/`RESTRICT` foreign key the provider reports, so the `other` safety
net does not report it twice. `MyModel.objects.for_user(user)`, when it
exists, decides whether the caller may open an item; without it, items are
never accessible.
