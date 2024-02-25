# Authentication APIs

### Unauthorized Attempt

**Status Code:** 401

**Response:**

```json
{
    "message": "Unauthorized"
}
```

### Login

```http
GET /login
```

Sample URL:
> <base_url>/login

Response: Auth0 login page

### Logout

```http
GET /logout
```

Sample URL:
> <base_url>/logout

Response: OK (redirect to Auth0 page)

### Signup

```http
GET /signup
```

Sample URL:
> <base_url>/signup

Response: Auth0 signup page

### Get User Profile

```http
GET /profile
```

Sample URL:
> <base_url>/unstract/<org_id>/profile

Response:

```json
{
    "user": {
        "id": "6",
        "email": "iamali003@gmail.com",
        "name": "Ali",
        "display_name": "Ali",
        "family_name": null,
        "picture": null
    }
}
```

### Password Reset

```http
POST /reset_password
```

Sample URL:
> <base_url>/unstract/<org_id>/reset_password

Response:

```json
{
    "status": "failed",
    "message": "user doesn't have Username-Password-Authentication"
}
```

### Get Organizations of User

```http
GET /organization
```

Sample URL:
> <base_url>/organization

Response:

```json
{
    "message": "success",
    "organizations": [
        {
            "id": "org_Z12elHhCcPH5rPD7",
            "display_name": "Personal Org",
            "name": "personal"
        },
        {
            "id": "org_CB46CBskR8BxFjVV",
            "display_name": "ali Test",
            "name": "ali1"
        }
    ]
}
```

### Select an Organization to Use

```http
POST /set
```

Sample URL:
> <base_url>/organization/<org_id>/set

Response:

```json
{
    "user": {
        "id": "6",
        "email": "iamali003@gmail.com",
        "name": "Ali",
        "display_name": "Ali",
        "family_name": null,
        "picture": null
    },
    "organization": {
        "display_name": "ali Test",
        "name": "ali1",
        "organization_id": "org_CB46CBskR8BxFjVV"
    }
}

```

### Get Organization Members

```http
GET /members
```

Sample URL:
> <base_url>/unstract/<org_id>/members

Response:

```json
{
    "message": "success",
    "members": [
        {
            "user_id": "google-oauth2|102763382532901780910",
            "email": "iamali003@gmail.com",
            "name": "",
            "picture": null
        }
    ]
}
```

### Get Organization Info

```http
GET /organization
```

Sample URL:
> <base_url>/unstract/<org_id>/organization

Response:

```json
{
    "message": "success",
    "organization": {
        "name": "ali1",
        "display_name": "ali Test",
        "organization_id": "org_CB46CBskR8BxFjVV",
        "created_at": "2023-06-26 04:42:40.905458+00:00"
    }
}
```

## Ref

- Postman Collection : [postaman collection link](https://api.postman.com/collections/24537488-9380ea92-d1e0-45f4-827c-c5cc9d0370b8?access_key=PMAT-01H3VGHTM9SR01MHXA95G1RTWB)
- By testing Postman
  - set cookies
  - set X-CSRFToken in header for POST request
