# Basic WorkFlow

`We can Add Workflows Here`

## Login

### Step

1. Login
2. Get Organizations
3. Set Organization
4. Use organizational APIs /unstract/<org_id>/

## Switch organization

1. Get Organizations
2. Set Organization
3. Use organizational APIs /unstract/<org_id>/

## Get current user and Organization data

- Use Get User Profile and  Get Organization Info APIs

## Signout

1.signout APi

## Organization list contract

`GET /api/v1/organization` returns the caller's organizations. The typed contract is the `organization_list` operation's `@extend_schema` annotation in `views.py`, read with drf-spectacular; it is not part of the published deployment API spec. This section states the rules the annotation can't. Example from a cloud deployment:

```json
{
  "message": "success",
  "organizations": [
    {
      "id": "org_abc",
      "display_name": "Zipstack",
      "name": "zipstack",
      "metadata": {},
      "role": "unstract_admin",
      "member_count": 40,
      "region": "US"
    }
  ]
}
```

- `id`, `display_name`, `name` and `metadata` are always present, in that order. `metadata` is always `null` in OSS. In cloud it holds the identity provider's organization metadata, or `null` when the organization has none.
- `role`, `member_count` and `region` are each **absent, never null**, when this deployment can't answer for that organization. In cloud, regions share one identity provider, so the list can name organizations with no data on this deployment.
- Absent means unknown. A client leaves the value out of the display and draws no conclusion from it: the same rows come back without the three fields when working them out fails (see below).

| Field | Present when | Value |
|---|---|---|
| `role` | The caller has a membership in the organization on this deployment. | The stored role: `admin` or `user` in OSS; `unstract_admin`, `unstract_user`, `unstract_supervisor` or `unstract_reviewer` in cloud. |
| `member_count` | The organization exists on this deployment and, where the deployment sets `REGION`, its metadata doesn't name a different region. An organization created before the stamp and not back-filled carries no region, so a local copy of one from another region still sends the copy's count. | The people the members page lists: the organization's member records on this deployment. Platform API key accounts and pending invitations are not counted. |
| `region` | The deployment sets `REGION`, and either the organization's metadata names a region or the organization exists on this deployment. | The region code (`US`, `EU`; `STAGING`, `DEV` or `INTEGRATION` outside production), from the metadata trimmed and uppercased, else this deployment's `REGION`. The client maps it to a label. OSS and on-prem never send it: their settings don't read `REGION`, whatever the environment sets. Cloud stamps `region` on an organization's metadata where it is created. An organization from another region that the user once opened here has a local copy; its row shows the home region and no `member_count`, since this deployment counts only the people who opened the copy. Organizations created before the stamp and not back-filled show the region of the deployment that answered. |

If working out these three fields fails, the list is returned without them and the failure is logged.

If the organizations can't be listed at all, the response is `412` and the session is logged out. For a known authorization error the body is `{"domain": ..., "code": ...}` with `code` one of `USF`, `USR`, `INE001`, `INE002` or `INS`; otherwise the body is empty.

## Last-used product preference

Each user has one last-used product, shared by all their organisations
(`UserProductPreference`, logic in `product_preference.py`).

- `GET /api/v1/users/me/product-preference/` returns `product` (`unstract`,
  `llm-whisperer`, `verticals` or `flow`, or null), `updated_at` and
  `has_chosen`.
- `PUT` the same URL with `{"product": "<id>"}` to store it. Unknown ids get a
  400. Service accounts get a 403.
- `GET /api/v1/session` also returns `last_product` and `has_chosen`.
- `has_chosen` is false until a product is first stored. Clients use it as the
  first-login signal.
- The backend never writes it on its own. The client is expected to `PUT` it
  (from the product switcher, and after a login that started from a product
  page via `selectedProduct`) before reading `session`. Because the write is
  client-side, it works the same for every auth plugin.
- The `product` column has a database check constraint, so only the ids above
  can be stored.

JSON Schemas for the responses and the request body are in `contract/`.
