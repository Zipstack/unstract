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
| `member_count` | The organization exists on this deployment. | The people the members page lists: the organization's member records on this deployment. Platform API key accounts and pending invitations are not counted. |
| `region` | The organization exists on this deployment and the deployment sets `REGION`. | The region code (`US`, `EU`; `STAGING`, `DEV` or `INTEGRATION` outside production). The client maps it to a label. OSS and on-prem never send it: their settings don't read `REGION`, whatever the environment sets. It is the region of the deployment that answered: an organization from another region that the user once opened here has a local copy, so it shows this region and this deployment's member count. |

If working out these three fields fails, the list is returned without them and the failure is logged.

If the organizations can't be listed at all, the response is `412` and the session is logged out. For a known authorization error the body is `{"domain": ..., "code": ...}` with `code` one of `USF`, `USR`, `INE001`, `INE002` or `INS`; otherwise the body is empty.
