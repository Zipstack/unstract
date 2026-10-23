# tenant_account_v2

## Profile contract

The current user's profile. All paths are organization-scoped: `/api/v1/unstract/<org_id>/users/profile/...`. The typed contract is the `@extend_schema` annotation on each view in `users_view.py` (operation ids `user_profile`, `user_profile_update`, `user_profile_photo`, `user_profile_photo_upload`, `user_profile_photo_delete`). It is not part of the published deployment API spec.

| Method and path | Request | Response |
|---|---|---|
| GET `users/profile/` | none | `{"user": {...}}`, the fields below |
| PATCH `users/profile/` | JSON, any of `display_name`, `language` | As GET |
| GET `users/profile/photo/` | none | The image, `image/png` or `image/jpeg`; 404 when there is none |
| POST `users/profile/photo/` | multipart, field `photo` | `{"photo_url": "..."}` |
| DELETE `users/profile/photo/` | none | 204, also when there was no photo |

### Fields

- `name`, `display_name`: the name the user set on their profile, or the identity provider's when they have not set one.
- `family_name`: null when the user has set a name, since that name is the whole name; otherwise the provider's.
- `picture`: `photo_url` when the user has a photo, otherwise the provider's picture (null in OSS).
- `photo_url`: the org-scoped URL of GET `users/profile/photo/` with a `?v=` version, the upload time in seconds; null when there is no photo.
- `language`: a BCP 47 tag. `en-US` is the only value accepted until translations exist.
- The other fields (`id`, `email`, `is_admin`, `role`, the onboarding flags, `organization_name`, `organization_id`) are unchanged.

### Rules

- `display_name` is trimmed and must be 1 to 64 characters. Empty or blank is refused.
- The photo is PNG or JPEG, up to 2 MB. The type is read from the bytes, so the file name does not matter. Anything else is refused.
- Errors use the backend's standard shape: `{"type": "validation_error", "errors": [{"code", "detail", "attr"}]}`, with `attr` naming the field.
- The edited name and photo are stored by Unstract and never written to the identity provider. They show wherever the backend builds user info through `AuthenticationController.get_user_info`: this endpoint and the set-organization response. Other responses, such as the cloud members list, build user details elsewhere and keep the provider's values.
- Photos are kept in the permanent file storage (`PERMANENT_REMOTE_STORAGE`) under `REMOTE_USER_PROFILE_PHOTO_PATH`, or, when that is unset, in a `user-profile-photos` folder beside `REMOTE_PROMPT_STUDIO_FILE_PATH`. With both unset, uploading a photo, or deleting one that exists, fails with a configuration error.
- The backend's `CacheControlMiddleware` sets `Cache-Control: no-store` on the photo as on other API responses, so browsers fetch it on each load.
