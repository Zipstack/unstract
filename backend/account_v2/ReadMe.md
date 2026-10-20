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

`GET /api/v1/organization` returns the caller's organizations. The schema is the `organization_list` operation's `@extend_schema` annotation in `views.py`; this section states the rules the schema can't.

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

- `id`, `display_name` and `name` are always present, in that order. `metadata` is present when the auth plugin supplies it (cloud).
- `role`, `member_count` and `region` are each **absent, never null**, when this deployment can't answer for that organization. In cloud, regions share one identity provider, so the list can name organizations with no data on this deployment.

| Field | Present when | Value |
|---|---|---|
| `role` | The caller has a membership in the organization on this deployment. | The stored role: `admin` or `user` in OSS; `unstract_admin`, `unstract_user`, `unstract_supervisor` or `unstract_reviewer` in cloud. |
| `member_count` | The organization exists on this deployment. | Members who have signed in on this deployment. Pending invitations are not counted. |
| `region` | The organization exists on this deployment and the deployment sets `REGION`. | The region code (`US`, `EU`; `STAGING`, `DEV` or `INTEGRATION` outside production). The client maps it to a label. OSS and on-prem never send it. |

If working out these three fields fails, the list is returned without them.
