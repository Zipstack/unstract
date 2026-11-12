# Resource usage

Reports what uses each saved adapter and connector: the "Used in" column, the
"used by no workflow" banner and the usage filter on the adapter and connector
lists, and the usage panel of a single profile.

The response shapes are published by the serializers in `serializers.py` and
the `@extend_schema` annotations in `schema.py`. This file covers what those
don't: the rule for what counts as used, and how another app adds references.

## Endpoints

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns |
|---|---|---|
| GET | `adapter/{id}/usage/` | What references the adapter |
| GET | `connector/{id}/usage/` | What references the connector, with the role it plays |
| GET | `adapter/`, `connector/` with `with_usage=true` | Each row gains `used_in_count` (connectors also `used_as`); a paged response gains `unused_count` |
| GET | `adapter/`, `connector/` with `unused=true` | Only profiles nothing uses, with the same keys |

Without `with_usage` or `unused` the lists are unchanged. `unused_count` counts
across all pages and, like `failing_count`, ignores the `unused`, `failing` and
`last_test_status` filters, so it stays put while the user toggles them.

Items the caller cannot open are still listed and counted, without id or name.

## What counts as used

A profile is used when something references it. The references are the ones
the delete guard refuses on, with the exceptions listed under the table.

| Reference | Group | Blocks delete |
|---|---|---|
| Adapter id, or adapter name before the lazy migration, anywhere in a workflow tool instance's `metadata` | `workflows` | yes |
| Prompt Studio project's summarize, monitor or challenge LLM | `prompt_studio_projects` | yes |
| Prompt Studio profile's LLM, embedding, vector DB or text extractor | `prompt_studio_projects` (the profile's project, or `other` when it has none) | yes |
| Connector on a workflow source or destination | `workflows`, with `role` | yes |
| Any other unclaimed `PROTECT` or `RESTRICT` foreign key to the profile | `other` | yes |
| A reference another app registers | that app's group | as registered |

- The `other` row is the safety net: a foreign key added later that blocks
  deletion is reported even before anyone gives it a group.
- A non-blocking reference is still counted, because deleting the profile
  would break what holds it.
- The API deployments and pipelines of each used workflow are listed in
  `deployments` and `pipelines` so the panel can show what would stop working,
  but they are not counted: the workflow already is.
- Being someone's **default** adapter is not usage. The guard does refuse to
  delete the caller's own default adapter, but that is per user, not a
  reference.
- The tool-instance check matches what the delete guard matches: string values
  anywhere in `metadata` (never keys) equal to the adapter's id or name, within
  the adapter's organisation.

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
net does not report it twice. `for_user(user)` on `MyModel`'s default manager,
when it exists, decides whether the caller may open an item; without it, items
are never accessible.
