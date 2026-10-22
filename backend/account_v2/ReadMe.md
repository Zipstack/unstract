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
