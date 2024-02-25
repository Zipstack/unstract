# FileManagement APIs

### List File

```http
GET /unstract/<org_id>/file?connector_id=<id>&path=<path>
```

Sample URL:
> <base_url>/unstract/org_KIYj2cJ9Yisdewi4/file?connector_id=11&path=/

### Download

```http
GET /unstract/<org_id>/file/download?connector_id=<id>&path=<path>
```

Sample URL:
> <base_url>/unstract/org_KIYj2cJ9Yisdewi4/file/download?connector_id=12&path=root/MaskTwo-design

### Upload

```http
POST /unstract/<org_id>/file/upload
```

Sample URL:
> <base_url>/unstract/org_KIYj2cJ9Yisdewi4/file/upload

- postman [url](https://zip-access-control-team.postman.co/workspace/My-Workspace~53945a45-432a-4093-811e-56d225da5b8c/request/24537488-2967e31d-7f8a-4dc5-8f09-0ab89e98b1c5?ctx=documentation)

#### Body

```json
{
    "file": <File> "<multiple files>",
    "connector_id": "<Connector Id>",
    "path": "<File location>",
}   
```
