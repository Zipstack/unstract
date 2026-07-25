# CAPTURE3 — security findings in the existing REST API

Two findings surfaced while surveying the tenant API surface to decide what the
platform MCP server should expose (PR #2207). **Neither is caused by that PR,
and neither is fixed by it** — both are pre-existing properties of the REST API,
captured here to be addressed separately.

---

## 1. Platform API keys are readable repeatedly, despite being documented "shown once"

**Severity:** medium — turns a write-once secret into a read-anytime one.

`PlatformApiKeyDetailSerializer` includes the full `key` field, and its own
docstring states the intent:

```python
# backend/platform_api/serializers.py:89-95
class PlatformApiKeyDetailSerializer(serializers.ModelSerializer):
    """Used for create/rotate responses where the full key is shown once."""

    class Meta:
        model = PlatformApiKey
        fields = ["id", "name", "key", "is_active"]
```

`get_serializer_class` routes `list` → masked, `create` → create serializer, and
`partial_update` → update serializer — but `retrieve` is not in that mapping and
instead selects the detail serializer explicitly:

```python
# backend/platform_api/views.py:59-62
def retrieve(self, request, *args, **kwargs):
    instance = self.get_object()
    serializer = PlatformApiKeyDetailSerializer(instance)
    return Response(serializer.data)
```

So `GET /api/v1/unstract/<org>/platform-api/keys/<pk>/` returns the full
plaintext key on **every** call, not once at creation.

**Why it matters.** `list` deliberately masks the key (`****-last4` via
`PlatformApiKeyListSerializer.get_key`), which shows the intent was for the
secret not to be freely readable. `retrieve` silently defeats that: anyone who
can reach the detail endpoint can recover any key in the organization at any
time, so a key leaked once cannot be reasoned about as "shown at creation only",
and rotation is the only remediation.

**Options to consider.**
- Mask `key` in `retrieve` (reuse the list serializer), and return the full key
  only from `create` and `rotate`, which is what the docstring already promises.
- If a re-read capability is genuinely wanted, make it an explicit, separately
  authorized action rather than the default detail representation.

**Related, not the same finding:** `GET /api/keys/api/<api_id>/` in `api_v2`
returns the full deployment API key and is gated at `IsOwnerOrSharedUser` rather
than owner-only — so any user a deployment is *shared with* can read its live
key. Worth reviewing alongside this one.

---

## 2. Two destructive endpoints are exposed over `GET`

**Severity:** medium — destructive actions reachable by link, prefetch or CSRF.

```python
# backend/file_management/urls.py:37-47
file_delete = FileManagementViewSet.as_view({"get": "delete"})
...
path("file/delete", file_delete, name="delete"),
```

```python
# backend/workflow_manager/workflow_v2/urls/workflow.py:25
workflow_clear_file_marker = WorkflowViewSet.as_view({"get": "clear_file_marker"})
```

`GET /api/v1/unstract/<org>/file/delete` deletes files, and
`GET /api/v1/unstract/<org>/workflow/<pk>/clear-file-marker/` clears file
markers. Both mutate state behind a verb that the entire web stack treats as
safe and idempotent.

**Why it matters.**
- **CSRF.** Django's CSRF protection does not apply to `GET`, so a cross-origin
  link, image tag or redirect can trigger either action using the victim's
  session. The usual "unsafe methods only" assumption does not hold here.
- **Prefetch and crawlers.** Browsers, link previews, and security scanners
  follow `GET` URLs speculatively. Any of these can fire a deletion nobody
  requested.
- **Caching and logs.** Intermediaries may cache or replay `GET`, and the URL
  (with parameters identifying what is deleted) lands in access logs and browser
  history.

Clearing file markers additionally forces re-processing of the affected files,
so it has a **cost** consequence as well as a data one.

**Options to consider.** Move both to `POST`/`DELETE`. This is a breaking change
for any existing caller, so it likely needs a deprecation window: accept both
verbs, log `GET` usage, then remove `GET` once callers have migrated.

---

## Not in scope here

Several other endpoints return decrypted credentials in their normal responses
(connector metadata, adapter provider keys, notification webhook tokens,
`platform_settings_v2` keys, the Postman collection download). Those are
intentional today insofar as the UI relies on them, and they are a broader
design question than these two — the platform MCP server simply does not wrap
any of them. See `backend/mcp_server/README.md` for that exclusion list.
