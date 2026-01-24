# SharePoint Connector Setup

## Authentication Modes

| Mode | Use Case | User Provides |
|------|----------|---------------|
| **OAuth** | Interactive access, user's OneDrive | Nothing (auto-filled after auth) |
| **Client Credentials** | Automation, service accounts | tenant_id, client_id, client_secret |

---

## Azure AD App Setup

1. Go to https://portal.azure.com → **Microsoft Entra ID** → **App registrations** → **New registration**
2. Name: `Unstract OneDrive Connector`, Account type: Single tenant
3. Copy from Overview: `client_id`, `tenant_id`
4. **Certificates & secrets** → New client secret → Copy VALUE as `client_secret`

### API Permissions

Add these in **API permissions** → **Add a permission** → **Microsoft Graph**:

| Permission | Type | Purpose |
|------------|------|---------|
| Files.ReadWrite.All | Delegated | OAuth access |
| Sites.ReadWrite.All | Delegated | OAuth access |
| Files.ReadWrite.All | Application | Client credentials |
| Sites.ReadWrite.All | Application | Client credentials |

**Important**: Click **"Grant admin consent"** after adding permissions.

For OAuth, also grant consent in **Enterprise applications** → Your app → **Permissions** → **Grant admin consent**.

---

## Configuration

### site_url Usage

| Scenario | site_url Value |
|----------|----------------|
| OneDrive (personal) | Empty string `""` |
| SharePoint site | `https://company.sharepoint.com/sites/sitename` |

**Note**: Never use `-my.sharepoint.com` URLs directly. For OneDrive, leave site_url empty.

### OAuth Settings
```python
settings = {
    "access_token": "<auto-filled>",
    "refresh_token": "<auto-filled>",
    "site_url": "",
}
```

### Client Credentials Settings
```python
settings = {
    "tenant_id": "xxx",
    "client_id": "xxx",
    "client_secret": "xxx",
    "site_url": "",
    "user_email": "user@company.com",  # Required for OneDrive access
}
```

### Backend Environment (for OAuth)
```bash
AZUREAD_TENANT_OAUTH2_KEY=<client_id>
AZUREAD_TENANT_OAUTH2_SECRET=<client_secret>
AZUREAD_TENANT_OAUTH2_TENANT_ID=<tenant_id>
```

---

## Testing

```bash
# All tests
uv run pytest unstract/connectors/tests/filesystems/test_sharepoint_fs.py -v

# Integration test
uv run pytest unstract/connectors/tests/filesystems/test_sharepoint_fs.py::TestSharePointFSIntegration::test_write_file_to_folder -v -s
```

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Need admin approval" | Grant consent in both App registrations AND Enterprise applications |
| 401 Unauthorized | Check Application permissions are granted (not just Delegated) |
| OneDrive access fails | Leave `site_url` empty, ensure `user_email` is set |
